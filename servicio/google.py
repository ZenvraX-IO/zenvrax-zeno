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

#: LOS BUZONES QUE SE CONECTAN. Uno por cada cuenta de Google de verdad. Se declaran aqui y no se
#: descubren: un buzon que aparezca solo no deberia poder conectarse.
CUENTAS = {
    "zenvrax": os.environ.get("ZENO_CORREO_ZENVRAX", "ghidalgo@zenvrax.com"),
}

#: LAS DIRECCIONES QUE NO SON UN BUZON APARTE. Medido el 2026-09-27: `ghidalgo@gutlyn.com` es un
#: ALIAS de `ghidalgo@zenvrax.com` dentro del mismo Workspace, no una cuenta distinta. Las dos
#: autorizaciones devolvian el mismo buzon.
#:
#: Estan declaradas porque sirven para UNA cosa: etiquetar de que negocio es cada correo, segun la
#: direccion a la que llego. Lo que NO hacen es pedir permiso, porque no hay nada que autorizar: el
#: buzon ya esta conectado. El operador (2026-09-27): *"si hay mas cuentas son del mismo workspace,
#: no tiene mucho sentido ponerla de GutLyn para conectar"*. Tenia razon: ese boton no podia hacer
#: nada, y el aviso de "sin conectar" decia que faltaba correo cuando no faltaba ninguno.
#:
#: El dia que GutLyn tenga cuenta de Google propia, se mueve su linea de aqui a CUENTAS y vuelve a
#: aparecer su boton. Por eso el codigo que lee sigue admitiendo varios buzones.
ALIAS = {
    "gutlyn": os.environ.get("ZENO_ALIAS_GUTLYN", "ghidalgo@gutlyn.com"),
}
#: ZONDRA NO ESTA, y es deliberado. Su direccion sigue recibiendo correo (2 de 14 en 30 dias), y al
#: verlo la añadi como tercer negocio por mi cuenta. El operador (2026-09-27): *"es solo Zenvrax y
#: Gutlyn, Zondra esta obsoleto"*. Una marca retirada no vuelve a existir porque le llegue correo:
#: eso lo decide el negocio, no la bandeja. Ese correo cae en Zenvrax, que es el dueño del buzon.


def direcciones() -> dict:
    """Todas las direcciones del operador, sean buzon o alias. Para etiquetar, no para conectar."""
    return {**CUENTAS, **ALIAS}

#: Tramo A y C: leer. Es con lo que se empieza y lo unico que se pide de serie.
PERMISOS_LEER = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid", "email",
]
#: Tramo B: dejar borradores EN el Gmail del operador, Y ENVIARLOS.
#:
#: OJO, ESTE COMENTARIO DECIA "No envia nada" Y ERA FALSO. Google describe `gmail.compose` como
#: *"Manage drafts and send emails"*: desde que el operador lo concedio el 27-sep, el permiso ya
#: permitia mandar correo. Lo unico que lo impedia era que no habia codigo que lo hiciera, y eso
#: no es una barrera, es una casualidad. Se creyo lo contrario un dia entero.
#:
#: Lo que de verdad protege el envio, desde el 28-sep, esta en el codigo: PIN obligatorio, vale de
#: un solo uso, renglon en el diario y ningun camino por voz.
PERMISO_BORRADOR = "https://www.googleapis.com/auth/gmail.compose"
#: Tramo D, la agenda: crear y mover citas. Sale al mundo, pero solo hacia el calendario.
PERMISO_AGENDA = "https://www.googleapis.com/auth/calendar.events"
#: Tramo E, el correo que se envia. ES OTRA COSA y va aparte, porque un correo mandado en tu nombre
#: llega a un cliente. Aprobar la agenda no aprueba esto: el operador aprobo el 2026-09-27 que Zeno
#: proponga citas, y nada mas. Juntarlos en un solo tramo habria pedido `gmail.send` de rebote.
PERMISO_ENVIAR = "https://www.googleapis.com/auth/gmail.send"
#: Todo lo que sale al mundo, junto, para que un test pueda comprobarlo de un vistazo.
PERMISOS_ESCRIBIR = [PERMISO_ENVIAR, PERMISO_AGENDA]


#: Cada tramo añade lo suyo al anterior. Se declaran asi, en una tabla, para que abrir uno no
#: arrastre nada que nadie ha aprobado: `agenda` NO incluye enviar correo.
TRAMOS = {
    "leer": [],
    "borrador": [PERMISO_BORRADOR],
    "agenda": [PERMISO_AGENDA],
    "escribir": [PERMISO_BORRADOR, PERMISO_AGENDA, PERMISO_ENVIAR],
}


#: Google CONCEDE los dos permisos de OpenID con su nombre largo, aunque se pidan con el corto.
#: Comparar las cadenas tal cual decia que faltaban `email` y `profile` para siempre, y el aviso de
#: "reconecta" se habria quedado puesto sin que reconectar lo quitara nunca: un aviso que no se
#: puede apagar deja de mirarse, y con el se deja de mirar el que si importaba.
_MISMO = {
    "email": "https://www.googleapis.com/auth/userinfo.email",
    "profile": "https://www.googleapis.com/auth/userinfo.profile",
}


def igual_que(permiso: str) -> set[str]:
    """Todas las formas de nombrar ese permiso. Para comparar lo pedido con lo concedido."""
    largo = _MISMO.get(permiso)
    corto = next((k for k, v in _MISMO.items() if v == permiso), None)
    return {permiso} | ({largo} if largo else set()) | ({corto} if corto else set())


def faltan(concedidos: list[str]) -> list[str]:
    """De lo que Zeno pide hoy, lo que esa cuenta NO ha concedido."""
    dados = set(concedidos or [])
    return [p for p in permisos() if not (igual_que(p) & dados)]


def permisos() -> list[str]:
    """Los permisos que se piden hoy. `ZENO_TRAMO` admite VARIOS separados por coma.

    Antes era uno solo y los tramos se pisaban: al abrir la agenda habria que elegir entre mover
    citas o dejar borradores, cuando son cosas distintas que no tienen por que ir juntas ni por que
    excluirse. Con la lista, `agenda,borrador` dice exactamente lo que esta abierto, y sigue sin
    abrir nada que no este escrito: un tramo desconocido no suma nada.
    """
    pedidos = [t.strip() for t in os.environ.get("ZENO_TRAMO", "leer").split(",") if t.strip()]
    fuera = list(PERMISOS_LEER)
    for tramo in pedidos:
        for permiso in TRAMOS.get(tramo, []):
            if permiso not in fuera:
                fuera.append(permiso)
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

def enlace_para_autorizar(negocio: str, estado: str = "") -> str:
    """La direccion a la que el operador va para dar permiso a UNA de sus cuentas.

    `estado` es el vale de un solo uso que pone el servicio. Viaja como parametro `state`, y por eso
    se recibe AQUI en vez de pegarlo luego al final de la direccion: pegarlo fuera dejaba el `state`
    dos veces, y Google rechaza el parametro repetido con "OAuth 2 parameters can only have a single
    value: state". Paso en la primera autorizacion real, el 2026-09-27.
    """
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
        # `select_account` ademas de `consent` porque sin el Google coge la sesion que ya haya abierta
        # en el navegador. Medido el 2026-09-27 con el operador: le cogia su cuenta personal y, al ser
        # una aplicacion INTERNA de la organizacion, Google respondia con el acceso bloqueado. Con
        # esto sale el selector y elige la cuenta que toca.
        "prompt": "select_account consent",
        "login_hint": CUENTAS[negocio],
        # `hd` es el filtro de verdad: limita el selector al dominio de ESA cuenta, asi que una
        # personal de gmail.com ni aparece. `login_hint` solo sugiere; esto acota.
        "hd": _dominio(CUENTAS[negocio]),
        "state": estado or negocio,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(parametros)


def _dominio(correo: str) -> str:
    """El dominio de una cuenta, que es lo que Google entiende por organizacion."""
    return correo.rsplit("@", 1)[-1] if "@" in correo else ""


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
    # A QUE BUZON ha dado permiso DE VERDAD, preguntandoselo a Google en vez de suponerlo. Medido el
    # 2026-09-27: `ghidalgo@gutlyn.com` resulto ser un ALIAS de `ghidalgo@zenvrax.com`, asi que las
    # dos autorizaciones daban el mismo buzon y Zeno pintaba cada correo dos veces. Sin este dato no
    # habia forma de saberlo desde dentro: los dos permisos parecian dos cuentas distintas.
    cofre[negocio]["buzon"] = _pregunta_el_buzon(negocio) or CUENTAS[negocio]
    _guarda_cofre(cofre)
    return {"negocio": negocio, "cuenta": CUENTAS[negocio],
            "buzon": cofre[negocio]["buzon"], "permisos": t.get("scope", "")}


def _pregunta_el_buzon(negocio: str) -> str:
    """El correo real del buzon al que se ha dado permiso. Cadena vacia si no se puede saber."""
    try:
        return str(pide(negocio, "https://gmail.googleapis.com/gmail/v1/users/me/profile")
                   .get("emailAddress") or "")
    except Exception:                                    # noqa: BLE001
        # No es motivo para tumbar la autorizacion recien concedida: se cae al valor supuesto y la
        # proxima lectura lo reintenta.
        return ""


def olvida(negocio: str) -> bool:
    """Quita el permiso de UNA cuenta. La otra sigue como estaba: esa es toda la gracia."""
    cofre = _lee_cofre()
    habia = cofre.pop(negocio, None) is not None
    _guarda_cofre(cofre)
    return habia


def conectadas() -> dict:
    """Que cuentas han dado permiso y con que alcance. Nunca devuelve los tokens."""
    cofre = _lee_cofre()
    return {n: {"cuenta": d.get("cuenta"),
                # El buzon REAL. Si coincide en dos negocios, es que uno es alias del otro.
                "buzon": d.get("buzon") or d.get("cuenta"),
                "permisos": d.get("permisos", "").split(),
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


def escribe(negocio: str, url: str, cuerpo: dict | None, metodo: str = "POST") -> dict:
    """LA UNICA puerta por la que Zeno escribe en Google. Usarla es un acto deliberado.

    Esta aparte de `pide` para que se vea de un vistazo quien escribe: hoy solo `citas.py`, y solo
    detras de una confirmacion del operador. Un test fija esa lista, porque el dia que alguien la
    llame desde otro sitio, lo que se escapa es un correo o una cita que otra persona ya ha visto.

    Si falta el permiso, Google responde 403 y se traduce a algo que se entiende, en vez de dejar un
    error crudo: la causa casi siempre es que el tramo de escritura no se ha abierto todavia.
    """
    # `cuerpo=None` para los DELETE: mandar un cuerpo vacio en un borrado no es lo mismo que no
    # mandar ninguno, y Google contesta 400 a lo primero.
    cabeceras = {"Authorization": "Bearer " + _acceso(negocio)}
    datos = None
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode()
        cabeceras["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise NoAutorizado(
                "Zeno todavia no tiene permiso para escribir en Google: hay que abrir el tramo "
                "de calendario (ZENO_TRAMO=escribir) y volver a autorizar la cuenta") from e
        raise
