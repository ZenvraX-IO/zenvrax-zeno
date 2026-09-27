# -*- coding: utf-8 -*-
"""Las dos cuentas de Google del operador: autorizar, guardar el permiso y refrescarlo.

DOS CUENTAS, DOS AUTORIZACIONES. `ghidalgo@zenvrax.com` y `ghidalgo@gutlyn.com` son cuentas de
Google distintas, y esa separacion ya existia antes de Zeno. Se respeta tal cual: cada una tiene su
permiso, su token y su caducidad. **La frontera entre los dos negocios la sostiene Google**, no un
`if` en este fichero, y revocar una no toca a la otra.

LOS PERMISOS SE PIDEN POR TRAMOS, del mas inocente al mas delicado, y cada tramo se usa un tiempo
antes de pedir el siguiente. El salto de naturaleza esta en el ultimo: hasta `calendar.readonly`, lo
peor que puede pasar si esto se filtra es que alguien LEA; con `gmail.send`, que alguien escriba a
los clientes del operador en su nombre. Por eso `send` no esta en la lista de serie y hay que
encenderlo a mano.

DONDE SE GUARDA EL PERMISO. En un fichero cifrado dentro del volumen de Zeno. Es la unica cosa que
Zeno guarda, y se guarda porque no hay alternativa: un permiso de Google que no persiste obliga a
volver a autorizar en cada reinicio. NO son datos de negocio, son credenciales, asi que no
contradicen la regla de no tener una tercera verdad: los correos NO se guardan, se leen y se
olvidan.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

#: UN CLIENTE OAUTH POR CUENTA, y no uno compartido. Medido el 2026-09-27: los dos dominios usan
#: Google Workspace (`zenvrax.com` y `gutlyn.com`), o sea son organizaciones distintas salvo que uno
#: sea dominio secundario del otro. Una aplicacion "interna" solo vale dentro de SU organizacion, y
#: una "externa" en modo prueba caduca el permiso cada 7 dias con los permisos de Gmail, que son
#: restringidos. Con un cliente por cuenta, cada una puede ser interna en su organizacion: sin
#: verificacion de Google y sin reautorizar cada semana.
#: Si las dos cuentas resultan estar en la MISMA organizacion, se pone el mismo par en las dos y ya.
def _cliente(negocio: str) -> tuple[str, str]:
    """El (id, secreto) del cliente OAuth de esa cuenta, con respaldo al comun."""
    suf = negocio.upper()
    ident = os.environ.get(f"GOOGLE_CLIENT_ID_{suf}") or os.environ.get("GOOGLE_CLIENT_ID", "")
    secreto = (os.environ.get(f"GOOGLE_CLIENT_SECRET_{suf}")
               or os.environ.get("GOOGLE_CLIENT_SECRET", ""))
    return ident, secreto
#: Con que clave se cifran los permisos en disco. Sin ella, Zeno no guarda nada.
CLAVE_COFRE = os.environ.get("ZENO_COFRE_KEY", "")
COFRE = pathlib.Path(os.environ.get("ZENO_COFRE", "/datos/google.cofre"))
VUELTA = os.environ.get("ZENO_URL_PUBLICA", "https://zeno.zenvrax.com") + "/api/google/vuelta"

#: Las dos cuentas del operador, cada una con su negocio. Se declaran aqui y no se descubren: una
#: cuenta que aparezca sola no deberia poder conectarse.
CUENTAS = {
    "zenvrax": os.environ.get("ZENO_CORREO_ZENVRAX", "ghidalgo@zenvrax.com"),
    "gutlyn": os.environ.get("ZENO_CORREO_GUTLYN", "ghidalgo@gutlyn.com"),
}

#: Tramo A y C: leer. Es con lo que se empieza y lo unico que se pide de serie.
PERMISOS_LEER = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid", "email",
]
#: Tramo B: dejar borradores EN el Gmail del operador. No envia nada.
PERMISO_BORRADOR = "https://www.googleapis.com/auth/gmail.compose"
#: Tramo D: lo que sale al mundo. Fuera de la lista a proposito.
PERMISOS_ESCRIBIR = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]


def permisos() -> list[str]:
    """Los permisos que se piden hoy. `ZENO_TRAMO` los va abriendo: leer | borrador | escribir."""
    tramo = os.environ.get("ZENO_TRAMO", "leer")
    fuera = list(PERMISOS_LEER)
    if tramo in ("borrador", "escribir"):
        fuera.append(PERMISO_BORRADOR)
    if tramo == "escribir":
        fuera += PERMISOS_ESCRIBIR
    return fuera


class SinConfigurar(RuntimeError):
    """Falta el cliente de Google o la clave del cofre. Se dice, no se finge que no hay cuentas."""


class NoAutorizado(RuntimeError):
    """Esa cuenta todavia no ha dado permiso, o lo ha retirado."""


# ---------------------------------------------------------------- el cofre

def _llave() -> bytes:
    if not CLAVE_COFRE:
        raise SinConfigurar("falta ZENO_COFRE_KEY: sin ella no se guardan permisos")
    return hashlib.sha256(CLAVE_COFRE.encode()).digest()


def _cifra(texto: str) -> bytes:
    """XOR con una llave derivada, y la salida en base64.

    Es cifrado simetrico simple a proposito: el fichero vive en un volumen del servidor al que solo
    llega root, y la defensa de verdad es esa. Esto evita que un token quede en claro en un backup
    o en un volcado, que es el riesgo real aqui.
    """
    llave = _llave()
    crudo = texto.encode()
    mezcla = bytes(b ^ llave[i % len(llave)] for i, b in enumerate(crudo))
    return base64.b64encode(mezcla)


def _descifra(datos: bytes) -> str:
    llave = _llave()
    crudo = base64.b64decode(datos)
    return bytes(b ^ llave[i % len(llave)] for i, b in enumerate(crudo)).decode()


def _lee_cofre() -> dict:
    if not COFRE.exists():
        return {}
    try:
        return json.loads(_descifra(COFRE.read_bytes()))
    except Exception:                                    # noqa: BLE001
        # Un cofre ilegible (clave cambiada, fichero a medias) se trata como "no hay permisos", no
        # como un error fatal: el operador vuelve a autorizar y ya. Callarlo seria peor, asi que
        # quien llame vera que no hay cuentas conectadas.
        return {}


def _guarda_cofre(datos: dict) -> None:
    COFRE.parent.mkdir(parents=True, exist_ok=True)
    COFRE.write_bytes(_cifra(json.dumps(datos)))
    try:
        COFRE.chmod(0o600)
    except Exception:                                    # noqa: BLE001
        pass


# ---------------------------------------------------------------- autorizar

def enlace_para_autorizar(negocio: str) -> str:
    """La direccion a la que el operador va para dar permiso a UNA de sus cuentas."""
    if negocio not in CUENTAS:
        raise NoAutorizado(f"no conozco el negocio {negocio!r}")
    ident, _ = _cliente(negocio)
    if not ident:
        raise SinConfigurar(f"falta el cliente OAuth de {negocio}: GOOGLE_CLIENT_ID_{negocio.upper()}")
    parametros = {
        "client_id": ident,
        "redirect_uri": VUELTA,
        "response_type": "code",
        "scope": " ".join(permisos()),
        # `offline` + `consent` para que Google entregue el token de refresco: sin el, el permiso
        # caduca en una hora y hay que volver a autorizar a mano cada vez.
        "access_type": "offline",
        "prompt": "consent",
        "login_hint": CUENTAS[negocio],
        "state": negocio,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(parametros)


def _pide_token(cuerpo: dict) -> dict:
    datos = urllib.parse.urlencode(cuerpo).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=datos, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def guarda_permiso(negocio: str, codigo: str) -> dict:
    """Cambia el codigo que devuelve Google por un permiso duradero y lo guarda."""
    if negocio not in CUENTAS:
        raise NoAutorizado(f"no conozco el negocio {negocio!r}")
    ident, secreto = _cliente(negocio)
    t = _pide_token({"code": codigo, "client_id": ident, "client_secret": secreto,
                     "redirect_uri": VUELTA, "grant_type": "authorization_code"})
    if not t.get("refresh_token"):
        # Sin refresco, el permiso dura una hora. Es un fallo de configuracion (falta `consent`) y
        # se dice ahora, no dentro de una hora cuando deje de funcionar sin motivo aparente.
        raise NoAutorizado("Google no ha dado permiso duradero: revisa access_type=offline")
    cofre = _lee_cofre()
    cofre[negocio] = {"refresh": t["refresh_token"], "acceso": t.get("access_token", ""),
                      "caduca": time.time() + int(t.get("expires_in", 3600)) - 60,
                      "permisos": t.get("scope", ""), "cuenta": CUENTAS[negocio]}
    _guarda_cofre(cofre)
    return {"negocio": negocio, "cuenta": CUENTAS[negocio], "permisos": t.get("scope", "")}


def olvida(negocio: str) -> bool:
    """Quita el permiso de UNA cuenta. La otra sigue como estaba: esa es toda la gracia."""
    cofre = _lee_cofre()
    habia = cofre.pop(negocio, None) is not None
    _guarda_cofre(cofre)
    return habia


def conectadas() -> dict:
    """Que cuentas han dado permiso y con que alcance. Nunca devuelve los tokens."""
    cofre = _lee_cofre()
    return {n: {"cuenta": d.get("cuenta"), "permisos": d.get("permisos", "").split(),
                "caduca_en_segundos": max(0, int(d.get("caduca", 0) - time.time()))}
            for n, d in cofre.items()}


def _acceso(negocio: str) -> str:
    """Un token de acceso valido, refrescandolo si hace falta."""
    cofre = _lee_cofre()
    d = cofre.get(negocio)
    if not d:
        raise NoAutorizado(f"{CUENTAS.get(negocio, negocio)} todavia no ha dado permiso")
    if d.get("acceso") and time.time() < d.get("caduca", 0):
        return d["acceso"]
    try:
        ident, secreto = _cliente(negocio)
        t = _pide_token({"refresh_token": d["refresh"], "client_id": ident,
                         "client_secret": secreto, "grant_type": "refresh_token"})
    except urllib.error.HTTPError as e:
        # 400 aqui casi siempre significa que el operador revoco el permiso desde su cuenta de
        # Google. Se borra el del cofre: dejarlo haria que Zeno reintentara para siempre.
        if e.code == 400:
            olvida(negocio)
            raise NoAutorizado(f"{CUENTAS.get(negocio)} ha retirado el permiso") from e
        raise
    d["acceso"] = t["access_token"]
    d["caduca"] = time.time() + int(t.get("expires_in", 3600)) - 60
    cofre[negocio] = d
    _guarda_cofre(cofre)
    return d["acceso"]


def pide(negocio: str, url: str) -> dict:
    """Un GET a la API de Google con el permiso de esa cuenta. Solo GET: leer."""
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _acceso(negocio)})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or "{}")
