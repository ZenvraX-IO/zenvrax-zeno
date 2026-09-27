# -*- coding: utf-8 -*-
"""El servicio de Zeno: sirve la aplicación y le da de comer lo que ya sabe leer.

QUE ES Y QUE NO. Es una fachada delgada. Toda la inteligencia está en dos sitios que ya existen y
están probados: `lector.py` (leer las dos colas y el corpus) y `catalogo/` (qué hace cada acción y
si es irreversible). Aquí solo se convierten en HTTP y se pone la sesión delante.

LO QUE NO HACE, y es la promesa de la fase J2-J3: **no ejecuta nada**. Ni una petición que no sea
GET hacia los dos sistemas. Los botones que ve el operador enlazan; pulsarlos de verdad es J4, y
entonces pasarán por el contrato de acciones, no por aquí.

LA SESION viene del cockpit (ver `sesion.py`): Zeno no tiene usuarios propios. Cada petición trae el
token del cockpit y se verifica contra él, con una caché de 60 s para no preguntar en cada pantalla.

`CockpitNoResponde` se traduce a **503** y no a 401 a propósito. Con 401, el front borraría el token
y echaría al operador al login cada vez que el cockpit se reinicia: es exactamente el incidente que
el propio cockpit tuvo en agosto de 2026 y por el que allí también devuelve 503.
"""
from __future__ import annotations

import os
import secrets
import sys
import time
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import lector                                    # noqa: E402
from servicio import (avisos, chat as chat_mod, citas, clave as clave_mod,  # noqa: E402
                      empuje, google, personal, ronda, sesion)

WEB = RAIZ / "web"
#: El chat gasta dinero (medido: ~$0,006 por pregunta). Nace APAGADO: se enciende cuando el
#: operador aprueba ese gasto recurrente, no por defecto. Ver `chat.py` cuando exista.
CHAT_ACTIVO = os.environ.get("ZENO_CHAT_ACTIVO", "0") == "1"

app = FastAPI(title="Zeno", docs_url=None, redoc_url=None, openapi_url=None)


def _quien(authorization: str):
    """La sesión de cada petición, traduciendo los dos fallos a códigos distintos."""
    token = authorization.split(" ", 1)[1] if authorization.lower().startswith("bearer ") else ""
    try:
        return sesion.quien_es(token), token
    except sesion.NoAutenticado as e:
        raise HTTPException(401, str(e)) from e
    except sesion.CockpitNoResponde as e:
        raise HTTPException(503, str(e)) from e


# ---------------------------------------------------------------- entrar

class Entrada(BaseModel):
    email: str
    password: str


class Segundo(BaseModel):
    challenge: str
    code: str


class Clave(BaseModel):
    clave: str


@app.post("/api/entrar")
async def entrar_con_clave(body: Clave):
    """La puerta de cada dia: UNA clave, sin segundo factor, y la sesion dura tres meses.

    El operador (2026-09-27): *"no se queda registrada y es un lio"*. Entrar pedia la contraseña del
    cockpit y encima el codigo del autenticador, varias veces al dia y desde el movil. El camino del
    cockpit sigue existiendo abajo, intacto.
    """
    correo = sesion.USUARIOS[0] if sesion.USUARIOS else ""
    try:
        return clave_mod.entrar(body.clave, correo)
    except clave_mod.ClaveNoConfigurada as e:
        raise HTTPException(503, str(e)) from e
    except clave_mod.ClaveMala as e:
        raise HTTPException(401, str(e)) from e


@app.get("/api/como_se_entra")
async def como_se_entra():
    """Que puerta enseñar en el login. Sin sesion: es lo primero que pregunta la pantalla."""
    return {"clave_propia": bool(clave_mod.CLAVE_HASH)}


@app.post("/api/login")
async def login(body: Entrada):
    """Paso 1. La respuesta es la del cockpit tal cual: si él pide segundo factor, se pide."""
    try:
        return sesion.entrar(body.email, body.password)
    except sesion.NoAutenticado as e:
        raise HTTPException(401, str(e)) from e
    except sesion.CockpitNoResponde as e:
        raise HTTPException(503, "No se puede entrar ahora: el cockpit no responde") from e


@app.post("/api/login/2fa")
async def login_2fa(body: Segundo):
    try:
        return sesion.entrar_2fa(body.challenge, body.code)
    except sesion.NoAutenticado as e:
        raise HTTPException(401, str(e)) from e
    except sesion.CockpitNoResponde as e:
        raise HTTPException(503, "No se puede entrar ahora: el cockpit no responde") from e


@app.post("/api/salir")
async def salir(authorization: str = Header(default="")):
    """Tira la caché de este token. La sesión de verdad la cierra el cockpit."""
    if authorization.lower().startswith("bearer "):
        sesion.olvidar(authorization.split(" ", 1)[1])
    return {"ok": True}


@app.get("/api/yo")
async def yo(authorization: str = Header(default="")):
    quien, _ = _quien(authorization)
    return {"email": quien.email, "role": quien.role}


# ---------------------------------------------------------------- lo que espera tu OK

@app.get("/api/pendientes")
async def pendientes(authorization: str = Header(default="")):
    """Las dos colas juntas, cada cosa con su contrato.

    `fallos` viaja SIEMPRE en la respuesta, aunque esté vacío, para que el front no tenga que
    adivinar si una lista corta es "hay poco" o "no he podido leer la mitad".
    """
    _quien(authorization)
    lista, fallos = lector.pendientes()
    # Dos preguntas distintas en una respuesta: las COLAS dicen cuanto queda en total y el feed dice
    # que hacer ahora. Con solo el feed parecia que habia una cosa pendiente cuando habia 113.
    colas, fallos_colas = lector.pendiente_completo()
    return {
        "fallos": fallos + fallos_colas,
        "colas": colas,
        "total_pendiente": sum(c["cuantos"] for c in colas),
        "pendientes": [{
            "negocio": p.negocio,
            "titulo": p.titulo,
            "cuerpo": p.cuerpo,
            "publica_algo": p.publica_algo,
            "cuesta_dinero": p.cuesta_dinero,
            "sin_contrato": p.sin_contrato,
            # `url` y `se_puede_abrir` viajan para que el front pueda ENLAZAR lo que abre. Sin
            # ellos los botones eran texto muerto: "ver preview no funciona", dicho por el operador
            # la primera vez que lo uso.
            "acciones": [{"etiqueta": a.etiqueta, "op": a.op, "efecto": a.efecto,
                          "coste_api": a.coste_api, "url": a.url,
                          "se_puede_abrir": a.se_puede_abrir}
                         for a in p.acciones],
        } for p in lista],
    }


# ---------------------------------------------------------------- lo primero de la mañana

def _contexto_de_hoy(plan, lo_torcido, negocios, personales):
    """Todo lo que Zeno sabe hoy, en texto, para que las tres lineas se escriban con criterio.

    La PANTALLA enseña poco (el foco y lo urgente, que es lo que se pidio), pero el resumen se
    escribe viendo todo: decidir bien necesita ver todo, enseñar bien necesita ver poco.
    """
    t = []
    if plan.get("foco"):
        t.append("LO PRIMERO SEGUN EL COCKPIT: " + plan["foco"]["titulo"])
    salto = chr(10)
    if plan.get("urgentes"):
        t.append("URGENTE:" + salto
                 + salto.join("  - " + u["titulo"] for u in plan["urgentes"]))
    if plan.get("resto"):
        t.append("TAMBIEN EN EL PLAN:" + salto
                 + salto.join("  - " + u["titulo"] for u in plan["resto"]))
    # `lo_torcido` y no `avisos`: `avisos` es el modulo que manda las notificaciones, y usar el
    # mismo nombre para una lista local lo tapaba dentro de esta funcion. Hoy no rompia nada porque
    # aqui no se usa el modulo, pero es una trampa puesta para el proximo que edite.
    if lo_torcido:
        t.append("SE HA SALIDO DE SITIO:" + salto + salto.join(
            f"  - [{a['negocio']}] {a['texto']}" for a in lo_torcido))
    for n in negocios:
        cifras = ", ".join(f"{k['k']} {k['v']}" for k in (n.get("kpis") or []))
        t.append(f"{n['nombre']}: {cifras or 'sin cifras'}. Espera tu OK: {n.get('pendiente', 0)}")
    if personales:
        t.append(personales)
    return (salto * 2).join(t) or "(hoy no hay datos: dilo)"


@app.get("/api/hoy")
async def api_hoy(narrar: bool = Query(default=True), authorization: str = Header(default="")):
    """Lo primero de la mañana: el foco, lo urgente, y tres lineas sobre que significa.

    Los DATOS no cuestan nada y van siempre. Las tres lineas cuestan una llamada a Haiku y se
    cachean POR DIA: abrir la aplicacion diez veces por la mañana no puede costar diez llamadas.
    Si el resumen falla, la pantalla sale igual con sus datos: el texto es el adorno, no la pieza.
    """
    _quien(authorization)
    plan, f1 = lector.plan_del_dia()
    lo_torcido, f2 = lector.alertas()
    negocios, f3 = lector.negocios()
    fallos = f1 + f2 + f3

    # Lo personal entra en el contexto del resumen aunque no se pinte aqui: una cita a las 10 cambia
    # que es lo primero del dia, y sin saberlo el resumen propone algo imposible.
    personales = ""
    try:
        datos, fp = personal.bandeja()
        hoy = [c for c in datos["agenda"]][:4]
        salto = chr(10)
        if hoy:
            personales = "TU AGENDA:" + salto + salto.join(
                f"  - {c['cuando'][:16]} {c['titulo']}" for c in hoy)
        if datos["correos"]:
            personales += salto + f"Correo sin leer: {len(datos['correos'])}"
        fallos += fp
    except Exception as e:                                # noqa: BLE001
        fallos.append(f"tu agenda: {type(e).__name__}")

    fuera = {"plan": plan, "avisos": lo_torcido, "fallos": fallos, "resumen": None}
    if narrar and CHAT_ACTIVO:
        try:
            fuera["resumen"] = chat_mod.resumen_de_la_manana(
                _contexto_de_hoy(plan, lo_torcido, negocios, personales))
        except (chat_mod.TopeAlcanzado, chat_mod.SinClaveDeIA) as e:
            fuera["fallos"].append(str(e))
        except Exception as e:                            # noqa: BLE001
            fuera["fallos"].append(f"el resumen escrito: {type(e).__name__}")
    return fuera


# ---------------------------------------------------------------- los avisos al movil

class Suscripcion(BaseModel):
    endpoint: str
    keys: dict


@app.get("/api/avisos")
async def avisos_estado(authorization: str = Header(default="")):
    """Si se pueden mandar avisos y a cuantos sitios. La clave publica la necesita el navegador."""
    _quien(authorization)
    return {"posible": empuje.configurado(), "llave": empuje.VAPID_PUBLICA,
            "suscritos": avisos.suscritos()}


@app.post("/api/avisos/suscribir")
async def avisos_suscribir(body: Suscripcion, authorization: str = Header(default="")):
    """Apunta este navegador. La suscripcion la crea el propio navegador, aqui solo se guarda."""
    _quien(authorization)
    try:
        return {"suscritos": avisos.apunta(body.model_dump())}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/avisos/quitar")
async def avisos_quitar(body: Suscripcion, authorization: str = Header(default="")):
    _quien(authorization)
    return {"habia": avisos.olvida(body.endpoint)}


@app.post("/api/avisos/probar")
async def avisos_probar(authorization: str = Header(default="")):
    """Manda UN aviso de prueba ahora. Es la unica forma de saber que el movil lo recibe de verdad:
    un permiso concedido en el navegador no garantiza que el aviso llegue a la pantalla."""
    _quien(authorization)
    try:
        return empuje.manda({"titulo": "Zeno", "cuerpo": "Los avisos funcionan.", "url": "/"})
    except empuje.SinLlaves as e:
        raise HTTPException(503, str(e)) from e


@app.get("/api/avisos/ensayo")
async def avisos_ensayo(authorization: str = Header(default="")):
    """Que avisaria la ronda ahora mismo, SIN mandar nada ni marcar nada como sonado."""
    _quien(authorization)
    return ronda.corre(seco=True)


# ---------------------------------------------------------------- los dos negocios

@app.get("/api/negocios")
async def api_negocios(authorization: str = Header(default="")):
    """Como van los dos negocios y que espera tu OK en cada uno.

    Ninguna fuente nueva: son los mismos datos con los que el chat ya contestaba. La diferencia es
    que mirarlos deja de costar una llamada a la API y una espera.
    """
    _quien(authorization)
    lista, fallos = lector.negocios()
    return {"negocios": lista, "fallos": fallos}


# ---------------------------------------------------------------- la documentación

@app.get("/api/buscar")
async def buscar(q: str = Query(..., min_length=2), authorization: str = Header(default="")):
    """El corpus. `modo` dice si respondió por significado o degradado a texto: el front lo enseña,
    porque contestar "no hay nada" con el servicio de embeddings caído es mentir con seguridad."""
    _quien(authorization)
    resultados, modo, fallos = lector.documentacion(q)
    return {"resultados": resultados, "modo": modo, "fallos": fallos}


# ---------------------------------------------------------------- el chat (apagado de serie)

class Pregunta(BaseModel):
    texto: str


@app.post("/api/chat")
async def chat(body: Pregunta, authorization: str = Header(default="")):
    """Contesta con Haiku sobre lo que Zeno ya sabe. Cada respuesta dice lo que ha costado.

    El contexto va precargado (lo pendiente, las colas y, si la pregunta lo pide, el corpus) en vez
    de darle herramientas: con herramientas cada pregunta serian varias llamadas, que es justo lo
    que encarece un chat.
    """
    _quien(authorization)
    if not CHAT_ACTIVO:
        # 501 y no 500: no está roto, es que no se ha encendido. Y el mensaje dice por qué.
        raise HTTPException(501, "El chat todavía no está encendido: gasta API y necesita tu OK")
    pregunta = (body.texto or "").strip()
    if len(pregunta) < 2:
        raise HTTPException(422, "escribe la pregunta")

    lista, fallos = lector.pendientes()
    colas, fallos_colas = lector.pendiente_completo()
    # El ESTADO va siempre. El operador pregunto por las ventas de GutLyn y el chat contesto que no
    # tenia el dato, teniendo Zeno la forma de leerlo: un asistente que no sabe como va el negocio
    # es una bandeja. Son dos llamadas mas por pregunta, y valen lo que cuestan.
    estado, fallos_estado = lector.estado()
    ventas, fallos_ventas = lector.ventas_gutlyn()
    fallos_colas = fallos_colas + fallos_estado + fallos_ventas
    # El corpus solo se consulta si la pregunta suena a documentacion: cada consulta de mas es
    # tiempo de respuesta y tokens de contexto que se pagan.
    documentos = []
    if any(p in pregunta.lower() for p in ("documenta", "sop", "regla", "como se", "cómo se",
                                           "donde esta", "dónde está", "procedimiento", "formula",
                                           "fórmula", "politica", "política")):
        documentos, _, mas_fallos = lector.documentacion(pregunta)
        fallos_colas = fallos_colas + mas_fallos
    try:
        return chat_mod.responde(pregunta, lista, colas, fallos + fallos_colas,
                                 documentos, estado, ventas)
    except chat_mod.TopeAlcanzado as e:
        raise HTTPException(429, f"Tope diario de preguntas alcanzado ({e})") from e
    except chat_mod.SinClaveDeIA as e:
        raise HTTPException(503, str(e)) from e


# ---------------------------------------------------------------- el correo y la agenda

#: Los permisos a medio conceder. La vuelta de Google llega por el NAVEGADOR, con una redirección, y
#: por tanto sin la cabecera del token: no hay forma de autenticarla como el resto. Así que el
#: permiso se empieza estando dentro (ahí sí hay sesión), eso apunta un vale de un solo uso, y la
#: vuelta solo se acepta si trae ese vale. Sin esto, cualquiera que adivinara la dirección de vuelta
#: podría atar SU cuenta de Google al Zeno del operador.
_VALES: dict[str, tuple[str, float]] = {}
_VALE_VIVE = 600.0          # diez minutos: lo que tarda alguien en pulsar "permitir"


def _vale_nuevo(negocio: str) -> str:
    ahora = time.time()
    for v, (_, nacido) in list(_VALES.items()):
        if ahora - nacido > _VALE_VIVE:
            _VALES.pop(v, None)
    vale = secrets.token_urlsafe(24)
    _VALES[vale] = (negocio, ahora)
    return vale


def _vale_se_gasta(vale: str) -> str:
    """Devuelve el negocio de ese vale y lo quema. Un vale sirve UNA vez."""
    negocio, nacido = _VALES.pop(vale, ("", 0.0))
    if not negocio or time.time() - nacido > _VALE_VIVE:
        raise HTTPException(400, "Esa autorización ha caducado: vuelve a empezar desde Zeno")
    return negocio


@app.get("/api/google/cuentas")
async def google_cuentas(authorization: str = Header(default="")):
    """Qué cuentas hay y cuáles han dado permiso. Nunca devuelve tokens (ver `google.conectadas`)."""
    _quien(authorization)
    conectadas = google.conectadas()
    cuentas = []
    for negocio, correo in google.CUENTAS.items():
        ident, _ = google._cliente(negocio)
        cuentas.append({"negocio": negocio, "cuenta": correo,
                        "conectada": negocio in conectadas,
                        # El buzon REAL al que apunta. Si dos cuentas traen el mismo, una es alias
                        # de la otra y el front tiene que decirlo en vez de fingir que son dos.
                        "buzon": conectadas.get(negocio, {}).get("buzon", ""),
                        # Sin cliente configurado el botón no puede funcionar: se dice, en vez de
                        # dejar que el operador pulse y se coma un error de Google.
                        "configurada": bool(ident),
                        "permisos": conectadas.get(negocio, {}).get("permisos", [])})
    # Los alias van APARTE de las cuentas. Mezclarlos era lo que ponia un boton Conectar donde no
    # hay nada que autorizar, y un aviso de "sin conectar" que decia que faltaba correo.
    alias = [{"negocio": n, "cuenta": c,
              "de": google.CUENTAS.get(next(iter(google.CUENTAS), ""), "")}
             for n, c in google.ALIAS.items()]
    return {"cuentas": cuentas, "alias": alias,
            "tramo": os.environ.get("ZENO_TRAMO", "leer")}


@app.post("/api/google/conectar")
async def google_conectar(negocio: str = Query(...), authorization: str = Header(default="")):
    """Devuelve la dirección de Google a la que ir a dar permiso a UNA de las dos cuentas."""
    _quien(authorization)
    if negocio not in google.CUENTAS:
        raise HTTPException(404, f"no conozco la cuenta {negocio}")
    try:
        # El vale va DENTRO, no pegado al final: dos `state` en la misma direccion hacen que Google
        # conteste "OAuth 2 parameters can only have a single value".
        enlace = google.enlace_para_autorizar(negocio, _vale_nuevo(negocio))
    except google.SinConfigurar as e:
        raise HTTPException(503, str(e)) from e
    return {"enlace": enlace}


@app.get("/api/google/vuelta")
async def google_vuelta(code: str = Query(default=""), state: str = Query(default=""),
                        error: str = Query(default="")):
    """Donde vuelve el navegador después de pulsar permitir. Sin sesión: la protege el vale.

    Devuelve HTML y no JSON porque quien llega aquí es una persona con un navegador, no el front.
    """
    if error:
        return _pagina_de_vuelta(f"Google no ha dado el permiso: {error}", False)
    negocio = _vale_se_gasta(state)
    try:
        hecho = google.guarda_permiso(negocio, code)
    except google.NoAutorizado as e:
        return _pagina_de_vuelta(str(e), False)
    except Exception as e:                                    # noqa: BLE001
        return _pagina_de_vuelta(f"No se ha podido guardar el permiso: {type(e).__name__}", False)
    return _pagina_de_vuelta(f"{hecho['cuenta']} conectada", True)


def _pagina_de_vuelta(mensaje: str, bien: bool):
    color = "#1f8a55" if bien else "#b23b2b"
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Zeno</title>"
        "<body style='margin:0;display:grid;place-items:center;min-height:100vh;background:#12110d;"
        "color:#f2eee4;font:16px -apple-system,system-ui,sans-serif;text-align:center;padding:24px'>"
        f"<div><p style='font-size:1.1rem;color:{color};margin:0 0 1rem'>{mensaje}</p>"
        "<a href='/' style='color:#e0a63c'>Volver a Zeno</a></div>")


@app.post("/api/google/olvidar")
async def google_olvidar(negocio: str = Query(...), authorization: str = Header(default="")):
    """Retira el permiso de UNA cuenta. La otra sigue igual."""
    _quien(authorization)
    return {"habia": google.olvida(negocio)}


class Propuesta(BaseModel):
    titulo: str
    desde: str
    minutos: int = citas.DURACION_POR_DEFECTO
    con: list[str] = []
    donde: str = ""


class Vale(BaseModel):
    vale: str


def _cual_buzon() -> str:
    """De que cuenta se lee la agenda. Hoy hay un buzon; el dia que haya dos, aqui se elige."""
    conectadas = google.conectadas()
    for negocio in google.CUENTAS:
        if negocio in conectadas:
            return negocio
    raise HTTPException(503, "No hay ninguna cuenta de Google conectada")


@app.get("/api/agenda/huecos")
async def agenda_huecos(minutos: int = Query(default=citas.DURACION_POR_DEFECTO, ge=10, le=480),
                        dias: int = Query(default=7, ge=1, le=60),
                        authorization: str = Header(default="")):
    """Donde cabe algo de esa duracion. Solo lee."""
    _quien(authorization)
    try:
        return {"huecos": citas.huecos(_cual_buzon(), minutos=minutos, dias=dias)}
    except google.NoAutorizado as e:
        raise HTTPException(503, str(e)) from e


@app.get("/api/agenda/choques")
async def agenda_choques(authorization: str = Header(default="")):
    """Las citas que se pisan. Solo lee."""
    _quien(authorization)
    try:
        return {"choques": citas.choques(_cual_buzon())}
    except google.NoAutorizado as e:
        raise HTTPException(503, str(e)) from e


@app.post("/api/agenda/proponer")
async def agenda_proponer(body: Propuesta, authorization: str = Header(default="")):
    """Prepara una cita y devuelve un vale. NO la crea: eso es el paso siguiente y lo pulsas tu."""
    _quien(authorization)
    try:
        return citas.propone(_cual_buzon(), body.titulo, body.desde, body.minutos,
                             body.con, body.donde)
    except citas.NoSePuede as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/agenda/confirmar")
async def agenda_confirmar(body: Vale, authorization: str = Header(default="")):
    """LO UNICO que crea la cita de verdad, y solo con un vale que salio de una propuesta tuya."""
    _quien(authorization)
    try:
        return citas.confirma(body.vale)
    except citas.NoSePuede as e:
        raise HTTPException(410, str(e)) from e
    except google.NoAutorizado as e:
        raise HTTPException(503, str(e)) from e


@app.get("/api/personal")
async def api_personal(authorization: str = Header(default="")):
    """El correo sin leer y las citas próximas de las dos cuentas.

    `fallos` viaja siempre, por lo mismo que en `/api/pendientes`: una bandeja corta sin aviso se
    lee como "tengo poco correo" cuando la verdad puede ser "falta una cuenta entera".
    """
    _quien(authorization)
    datos, fallos = personal.bandeja()
    return {"correos": datos["correos"], "agenda": datos["agenda"],
            "cuentas": datos["cuentas"], "fallos": fallos}


# ---------------------------------------------------------------- la aplicación

@app.get("/api/salud")
async def salud():
    """Sin sesión a propósito: es lo que mira el despliegue para saber si el contenedor vive."""
    return {"ok": True, "chat_activo": CHAT_ACTIVO}


if WEB.is_dir():
    app.mount("/img", StaticFiles(directory=str(WEB / "img")), name="img")

    @app.get("/manifest.webmanifest")
    async def manifiesto():
        return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/{resto:path}")
    async def aplicacion(resto: str = ""):
        """Todo lo que no es /api ni un fichero cae en la aplicación.

        Hace falta para que al recargar en `/buscar` no salga un 404: es el mismo motivo por el que
        una ruta que falta cae en la aplicación en el resto de los frontales de la casa.
        """
        fichero = WEB / resto
        if resto and fichero.is_file():
            return FileResponse(fichero)
        return FileResponse(WEB / "index.html")
