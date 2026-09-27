# -*- coding: utf-8 -*-
"""El login de Zeno: no tiene usuarios propios, los pide prestados al cockpit.

LA DECISION, y es la que evita lo peor. Zeno NO guarda usuarios, ni contraseñas, ni secretos de
firma, ni códigos de recuperación. Delega la identidad en el cockpit, que ya tiene login con doble
factor en producción desde hace meses.

Se descartaron las otras dos:

  · Usuarios propios en Zeno. Serían una TERCERA contraseña y un TERCER autenticador para el mismo
    operador, y una tercera base de datos con hashes que proteger. Se gana independencia y se paga
    con un sitio más donde perder las llaves.
  · Compartir la tabla `cockpit.users` por base de datos. Sería exactamente lo que acabamos de
    deshacer con Claire: un sistema leyendo la base de otro.

Y una tercera opción que también se descartó, más sutil: que Zeno emitiera SU token tras validar con
el cockpit. Eso le daría un secreto de firma propio, o sea criptografía que mantener y un token que
sobrevive a un `logout-all` del cockpit. Zeno no emite nada: reenvía el token del cockpit y lo
verifica contra él. Menos piezas, y cerrar la sesión en el cockpit cierra también la de Zeno.

LO QUE ESTO IMPLICA, dicho claro: si el cockpit está caído, no se puede ENTRAR en Zeno. Las sesiones
ya abiertas siguen mientras la caché aguante. Es el precio de no tener una tercera identidad, y es
el correcto: entrar es raro, consultar es lo de cada día.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from servicio import clave as clave_mod

COCKPIT = os.environ.get("ZENO_COCKPIT_URL", "https://cockpit.zenvrax.com/api")

#: Quien puede entrar en Zeno. El operador (2026-09-27): *"Zeno solo tendra un unico usuario que soy
#: yo"*. Eso no es solo una nota de producto, es una GUARDA: el cockpit puede tener mas usuarios
#: algun dia (ya tiene roles owner/operator), y sin esta lista cualquiera de ellos entraria tambien
#: en el asistente, que es la pieza que en J4 va a ejecutar acciones que publican.
#: Vacio = cualquiera con sesion valida del cockpit. Se deja asi por defecto para que un entorno de
#: pruebas no se quede fuera, y en produccion se pone el correo del operador.
USUARIOS = [u.strip().lower() for u in os.environ.get("ZENO_USUARIOS", "").split(",") if u.strip()]

#: Cuánto se fía Zeno de un token ya verificado antes de volver a preguntar al cockpit.
#: 60 s es el equilibrio: sin caché, cada pantalla dispara una llamada de más; con mucha, una sesión
#: revocada seguiría entrando demasiado rato. El cockpit ya invalida por `token_version`.
CACHE_SEGUNDOS = 60

_verificados: dict[str, tuple[float, "Quien"]] = {}


@dataclass(frozen=True)
class Quien:
    user_id: str
    role: str
    email: str = ""


class NoAutenticado(RuntimeError):
    """El token no vale, o el cockpit dice que no. Nunca se traga: Zeno no deja pasar por si acaso."""


class CockpitNoResponde(RuntimeError):
    """No se ha podido preguntar. Es DISTINTO de "no autenticado" a propósito.

    Confundirlos tiene las dos consecuencias malas: tratarlo como no autenticado echa al operador de
    una sesión válida cada vez que el cockpit se reinicia (ya pasó en el propio cockpit, agosto de
    2026, y por eso allí devuelve 503 y no 401); tratarlo como autenticado deja entrar sin comprobar.
    """


def _pide(ruta: str, cuerpo: dict | None = None, cabeceras: dict | None = None) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    cab = {"Content-Type": "application/json", "Accept": "application/json"}
    cab.update(cabeceras or {})
    req = urllib.request.Request(COCKPIT.rstrip("/") + ruta, data=datos,
                                 method="POST" if cuerpo is not None else "GET", headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = (json.loads(e.read() or "{}") or {}).get("detail", "")
        except Exception:                                        # noqa: BLE001
            pass
        if e.code in (401, 403, 429):
            raise NoAutenticado(detalle or f"el cockpit responde {e.code}") from e
        raise CockpitNoResponde(f"el cockpit responde {e.code}") from e
    except Exception as e:                                       # noqa: BLE001
        raise CockpitNoResponde(f"{type(e).__name__} hablando con el cockpit") from e


def entrar(email: str, password: str) -> dict:
    """Paso 1. Devuelve {'token': ...} o {'twofa_required': True, 'challenge': ...}.

    No se toca la respuesta del cockpit: si él pide segundo factor, Zeno pide segundo factor. Zeno no
    puede relajar una comprobación de seguridad que no es suya.
    """
    return _pide("/auth/login", {"email": email, "password": password})


def entrar_2fa(challenge: str, code: str) -> dict:
    """Paso 2. Devuelve {'token': ...} con el código del MISMO autenticador que el cockpit."""
    return _pide("/auth/login/2fa", {"challenge": challenge, "code": code})


def quien_es(token: str, ahora=None) -> Quien:
    """Quien trae ese token. Vale el del cockpit y vale el de la clave propia de Zeno.

    Los tokens de Zeno se reconocen por su prefijo y se verifican AQUI, sin salir a la red: son
    firmados, asi que no hace falta preguntar a nadie y la sesion sobrevive a que el cockpit este
    caido. Los del cockpit siguen el camino de siempre.
    """
    if not token:
        raise NoAutenticado("sin token")
    if clave_mod.es_de_zeno(token):
        try:
            correo = clave_mod.lee(token)
        except (clave_mod.ClaveMala, clave_mod.ClaveNoConfigurada) as e:
            raise NoAutenticado(str(e)) from e
        # La misma guarda que abajo: un token de Zeno tampoco esquiva la lista de quien puede entrar.
        if USUARIOS and correo.lower() not in USUARIOS:
            raise NoAutenticado("esta cuenta no tiene acceso a Zeno")
        return Quien(user_id="zeno", role="owner", email=correo)
    ahora = ahora if ahora is not None else time.monotonic()
    cacheado = _verificados.get(token)
    if cacheado and ahora - cacheado[0] < CACHE_SEGUNDOS:
        return cacheado[1]
    datos = _pide("/auth/me", cabeceras={"Authorization": f"Bearer {token}"})
    quien = Quien(user_id=str(datos.get("id") or datos.get("user_id") or ""),
                  role=str(datos.get("role") or "operator"),
                  email=str(datos.get("email") or ""))
    if not quien.user_id:
        # El cockpit contestó 200 pero sin identidad. Dejar pasar esto seria dar por bueno cualquier
        # 200 que venga de donde sea.
        raise NoAutenticado("el cockpit no ha dicho quien es")
    if USUARIOS and quien.email.lower() not in USUARIOS:
        # Sesion valida del cockpit, pero de alguien que no es el operador. Se rechaza ANTES de
        # cachear: si no, el primer rechazado quedaria guardado como verificado.
        raise NoAutenticado("esta cuenta no tiene acceso a Zeno")
    _verificados[token] = (ahora, quien)
    return quien


def olvidar(token: str) -> None:
    """Salir: se tira la caché de ese token. La sesión de verdad la cierra el cockpit."""
    _verificados.pop(token, None)


def limpiar_cache() -> None:
    _verificados.clear()
