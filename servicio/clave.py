# -*- coding: utf-8 -*-
"""La clave propia de Zeno: una sola, sin segundo factor, y la sesión dura tres meses.

POR QUE EXISTE, porque contradice una decisión que estaba escrita a propósito. `sesion.py` dice que
Zeno no tiene usuarios propios y que no emite tokens, y las razones siguen siendo buenas: una
identidad menos que mantener, y cerrar sesión en el cockpit cerraba también la de Zeno.

Lo que cambió es el uso real. Zeno se abre desde el móvil varias veces al día, y entrar pedía la
contraseña del cockpit MAS el código de seis cifras del autenticador. El operador (2026-09-27): *"no
se queda registrada y es un lio"*. Una puerta que cuesta cruzar se deja de cruzar, y entonces no
importa lo elegante que sea el diseño de dentro.

QUE SE HA CONSERVADO de la decisión original, para que esto no se convierta en la tercera identidad:

  · **No hay tabla de usuarios.** Hay UNA clave, y en el servidor vive solo su hash.
  · **No hay recuperación, ni correo, ni preguntas.** Si se pierde, se genera otra. Un flujo de
    recuperación es más superficie de ataque que la propia clave.
  · **El camino del cockpit sigue entero.** Esta clave se suma, no sustituye: un token del cockpit
    vale igual, así que si esto se quiere quitar algún día, se borra la variable y ya.

EL RIESGO QUE SE ACEPTA, dicho claro: una sola clave sin segundo factor en una dirección pública. Se
compensa con tres cosas medibles: el hash es scrypt (caro de probar en masa), hay freno tras varios
fallos, y con los permisos de hoy lo peor que se alcanza al entrar es LEER. El día que J4 ejecute
acciones que publican, esto se revisa.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

#: El hash de la clave, con su sal. Formato `scrypt$<sal_hex>$<hash_hex>`. En el servidor solo vive
#: esto: la clave en claro no se guarda en ningún sitio, ni aquí ni en el `.env`.
CLAVE_HASH = os.environ.get("ZENO_CLAVE_HASH", "")

#: Coste del scrypt. 2**15 tarda del orden de 0,1 s por intento: imperceptible al entrar, y convierte
#: probar un diccionario en algo que no acaba.
#: `maxmem` hay que declararlo: con n=2**15 y r=8 scrypt pide 32 MB, y OpenSSL trae un tope de serie
#: justo ahi, asi que sin esto la llamada falla con "memory limit exceeded". Lo encontro un test, no
#: el servidor: sin el, el primer intento de entrar en produccion habria dado un 500 sin explicacion.
_N, _R, _P = 2 ** 15, 8, 1
_MAXMEM = 96 * 1024 * 1024

#: Cuánto dura la sesión. Tres meses: es el número que hace que entrar sea raro, que es justo el
#: problema que esto resuelve. El token se puede invalidar en bloque cambiando la clave.
DURACION = 90 * 24 * 3600

#: Freno a la fuerza bruta. En memoria a propósito: un reinicio lo borra, y aun así sirve, porque lo
#: que frena es el intento número once seguido, no una campaña de meses.
TOPE_FALLOS = 8
CASTIGO = 900.0                     # quince minutos
_fallos: list[float] = []


class ClaveNoConfigurada(RuntimeError):
    """No hay clave puesta. Se dice, en vez de dejar entrar o de fingir que la clave es mala."""


class ClaveMala(RuntimeError):
    """La clave no es la que es, o se ha probado demasiadas veces seguidas."""


def _firma_llave() -> bytes:
    """Con qué se firman los tokens de Zeno.

    Se deriva del hash de la clave, no de un secreto nuevo: así **cambiar la clave invalida todas
    las sesiones abiertas** sin tener que llevar una lista de tokens vivos, y no hay un secreto más
    que rotar. El `sha256` con etiqueta evita que la misma cadena sirva para dos cosas distintas.
    """
    if not CLAVE_HASH:
        raise ClaveNoConfigurada("falta ZENO_CLAVE_HASH")
    return hashlib.sha256(("firma-de-sesion|" + CLAVE_HASH).encode()).digest()


def cifra_clave(clave: str) -> str:
    """El hash que se guarda en el `.env`. Se usa al generar la clave, nunca al entrar."""
    sal = os.urandom(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32,
                       maxmem=_MAXMEM)
    return f"scrypt${sal.hex()}${h.hex()}"


def _acierta(clave: str) -> bool:
    try:
        etiqueta, sal_hex, esperado = CLAVE_HASH.split("$")
    except ValueError:
        raise ClaveNoConfigurada("ZENO_CLAVE_HASH no tiene el formato scrypt$sal$hash") from None
    if etiqueta != "scrypt":
        raise ClaveNoConfigurada(f"no sé comprobar un hash de tipo {etiqueta!r}")
    h = hashlib.scrypt(clave.encode(), salt=bytes.fromhex(sal_hex), n=_N, r=_R, p=_P,
                       dklen=32, maxmem=_MAXMEM)
    # `compare_digest` y no `==`: comparar cadenas corta en el primer byte distinto, y ese tiempo
    # distinto es por donde se adivina un hash byte a byte.
    return hmac.compare_digest(h.hex(), esperado)


def _frenado(ahora: float) -> bool:
    global _fallos
    _fallos = [t for t in _fallos if ahora - t < CASTIGO]
    return len(_fallos) >= TOPE_FALLOS


def entrar(clave: str, correo: str = "", ahora: float | None = None) -> dict:
    """Cambia la clave por un token de Zeno. Lanza ClaveMala o ClaveNoConfigurada."""
    ahora = time.time() if ahora is None else ahora
    if not CLAVE_HASH:
        raise ClaveNoConfigurada("Zeno no tiene clave propia puesta todavía")
    if _frenado(ahora):
        raise ClaveMala("demasiados intentos seguidos: espera un cuarto de hora")
    if not _acierta(clave or ""):
        _fallos.append(ahora)
        raise ClaveMala("esa no es la clave")
    _fallos.clear()
    return {"token": emite(correo, ahora), "email": correo}


def emite(correo: str, ahora: float | None = None) -> str:
    """Un token firmado. Sin estado en el servidor: sobrevive a un reinicio del contenedor.

    Guardar las sesiones en memoria era exactamente el fallo que el operador notaba: cada despliegue
    de Zeno lo echaba fuera.
    """
    ahora = time.time() if ahora is None else ahora
    cuerpo = base64.urlsafe_b64encode(
        json.dumps({"c": correo, "exp": int(ahora + DURACION)}).encode()).decode().rstrip("=")
    firma = hmac.new(_firma_llave(), cuerpo.encode(), hashlib.sha256).hexdigest()[:32]
    return f"z1.{cuerpo}.{firma}"


def es_de_zeno(token: str) -> bool:
    """Si este token lo emitió Zeno. Lo usa `sesion` para no ir a preguntar al cockpit por él."""
    return token.startswith("z1.")


def lee(token: str, ahora: float | None = None) -> str:
    """El correo que lleva un token de Zeno, o ClaveMala. Comprueba la firma ANTES de leer nada."""
    ahora = time.time() if ahora is None else ahora
    partes = token.split(".")
    if len(partes) != 3 or partes[0] != "z1":
        raise ClaveMala("token con forma desconocida")
    _, cuerpo, firma = partes
    esperada = hmac.new(_firma_llave(), cuerpo.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(firma, esperada):
        raise ClaveMala("la firma del token no cuadra")
    try:
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    except Exception:                                            # noqa: BLE001
        raise ClaveMala("token ilegible") from None
    if float(datos.get("exp", 0)) < ahora:
        raise ClaveMala("la sesión ha caducado")
    return str(datos.get("c") or "")


# ---------------------------------------------------------------- la segunda llave

#: LA LLAVE DE LO IRREVERSIBLE. Hash de un PIN corto, con el mismo formato que la clave.
#:
#: POR QUE EXISTE Y POR QUE NO ES OTRO LOGIN. Al poner la clave propia quedo escrito aqui mismo:
#: "el dia que J4 ejecute acciones que publican, esto se revisa". Ese dia es hoy. Lo que cambia no
#: es la puerta, es lo que hay detras: hasta ahora entrar significaba LEER, y ahora significa poder
#: publicar en LinkedIn en nombre del operador.
#:
#: La salida facil seria pedir segundo factor al entrar, y seria la equivocada: es justo la
#: friccion que el operador quito porque le impedia usar Zeno ("no se queda registrada y es un
#: lio"). Una puerta que cuesta cruzar se deja de cruzar, y entonces no protege nada porque no hay
#: nada dentro que se use.
#:
#: Asi que el candado se mueve de sitio: entrar sigue siendo una clave, y lo IRREVERSIBLE pide este
#: PIN aparte. Consultar cuesta lo mismo que antes; publicar cuesta cuatro digitos.
PIN_HASH = os.environ.get("ZENO_PIN_HASH", "")

#: Cuanto vale un PIN acertado antes de volver a pedirlo. Diez minutos: aprobar ocho posts seguidos
#: no puede pedir ocho veces el PIN, y dejarlo abierto toda la sesion lo convertiria en un adorno.
GRACIA = float(os.environ.get("ZENO_PIN_GRACIA", "600"))

#: El PIN es corto, asi que el freno importa mas que en la clave: cuatro digitos son diez mil
#: combinaciones y sin freno se prueban en un rato.
TOPE_PIN = 5
CASTIGO_PIN = 900.0
_fallos_pin: list[float] = []
#: Cuando se acerto por ultima vez, por sesion. En memoria a proposito: un reinicio cierra la
#: gracia, que es el lado seguro del fallo.
_abierto: dict[str, float] = {}


class PinMalo(RuntimeError):
    """El PIN no es, o se ha probado demasiadas veces seguidas."""


def hay_pin() -> bool:
    return bool(PIN_HASH)


def _acierta_pin(pin: str) -> bool:
    try:
        etiqueta, sal_hex, esperado = PIN_HASH.split("$")
    except ValueError:
        raise ClaveNoConfigurada("ZENO_PIN_HASH no tiene el formato scrypt$sal$hash") from None
    if etiqueta != "scrypt":
        raise ClaveNoConfigurada(f"no se comprobar un hash de tipo {etiqueta!r}")
    h = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(sal_hex), n=_N, r=_R, p=_P,
                       dklen=32, maxmem=_MAXMEM)
    return hmac.compare_digest(h.hex(), esperado)


def abre_con_pin(sesion: str, pin: str, ahora: float | None = None) -> float:
    """Comprueba el PIN y abre la ventana de gracia. Devuelve hasta cuando vale."""
    global _fallos_pin
    ahora = time.time() if ahora is None else ahora
    if not PIN_HASH:
        raise ClaveNoConfigurada("no hay PIN puesto para las acciones que publican")
    _fallos_pin = [t for t in _fallos_pin if ahora - t < CASTIGO_PIN]
    if len(_fallos_pin) >= TOPE_PIN:
        raise PinMalo("demasiados intentos: espera un cuarto de hora")
    if not _acierta_pin(pin or ""):
        _fallos_pin.append(ahora)
        raise PinMalo("ese no es el PIN")
    _fallos_pin.clear()
    _abierto[sesion] = ahora
    return ahora + GRACIA


def abre_con_rostro(sesion: str, ahora: float | None = None) -> float:
    """Abre la misma ventana que el PIN, pero porque el telefono ha comprobado la cara.

    NO es rebajar la barrera. El PIN son cuatro cifras que se pueden mirar por encima del hombro y
    que el operador escribe en el movil, en la calle; Face ID es biometria comprobada por el chip
    del telefono y firmada con una clave que no sale de el. Lo que se exige es lo mismo: demostrar
    otra vez que eres tu, en el momento, antes de lo que no se deshace.

    Quien llama tiene que haber verificado la firma ANTES. Esta funcion no comprueba nada: solo
    abre la ventana, igual que `abre_con_pin` hace despues de acertar.
    """
    ahora = time.time() if ahora is None else ahora
    _abierto[sesion] = ahora
    return ahora + GRACIA


def pin_abierto(sesion: str, ahora: float | None = None) -> bool:
    """Si esta sesion ya puso el PIN hace poco."""
    ahora = time.time() if ahora is None else ahora
    return ahora - _abierto.get(sesion, 0.0) < GRACIA


def cierra_pin(sesion: str) -> None:
    """Cierra la ventana a mano. Lo usa salir, y cualquiera que quiera dejarlo cerrado."""
    _abierto.pop(sesion, None)
