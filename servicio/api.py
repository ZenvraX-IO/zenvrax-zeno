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
                      correo, diario, ejecutor, empuje, google, memoria, ordenes,
                      personal, ronda, rostro, sesion)

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


class Rostro(BaseModel):
    #: Lo que devuelve el navegador tal cual. No se toca aqui: lo comprueba la libreria.
    respuesta: dict
    apodo: str = ""


class Clave(BaseModel):
    clave: str


@app.post("/api/entrar")
async def entrar_con_clave(body: Clave):
    """La puerta de cada dia: UNA clave, sin segundo factor, y la sesion dura tres meses.

    El operador (2026-09-27): *"no se queda registrada y es un lio"*. Entrar pedia la contraseña del
    cockpit y encima el codigo del autenticador, varias veces al dia y desde el movil. El camino del
    cockpit sigue existiendo abajo, intacto.
    """
    quien = sesion.USUARIOS[0] if sesion.USUARIOS else ""
    try:
        return clave_mod.entrar(body.clave, quien)
    except clave_mod.ClaveNoConfigurada as e:
        raise HTTPException(503, str(e)) from e
    except clave_mod.ClaveMala as e:
        raise HTTPException(401, str(e)) from e


@app.get("/api/rostro")
async def rostro_estado():
    """Si hay Face ID dado de alta. SIN sesion: es lo que decide que enseña el login."""
    return {"hay": rostro.hay(), "cuantos": rostro.cuantas()}


@app.get("/api/rostro/entrar")
async def rostro_entrar_reto():
    """El reto para entrar. Sin sesion, por definicion: esto ES la puerta."""
    try:
        return rostro.entrada_empieza()
    except rostro.NoVale as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/rostro/entrar")
async def rostro_entrar(body: Rostro):
    """Entra con la cara. Comprueba la firma y, solo entonces, emite la sesion de siempre.

    El token lo emite `clave`, no `rostro`: dos sitios que emiten sesiones son dos sitios que
    caducan distinto, y del segundo nadie se acuerda al cambiar el primero.
    """
    try:
        rostro.entrada_termina(body.respuesta)
    except rostro.NoVale as e:
        raise HTTPException(401, str(e)) from e
    quien = sesion.USUARIOS[0] if sesion.USUARIOS else ""
    return {"token": clave_mod.emite(quien), "email": quien}


@app.get("/api/rostro/alta")
async def rostro_alta_reto(authorization: str = Header(default="")):
    """El reto para dar de alta este telefono. CON sesion: dar de alta una llave nueva exige haber
    entrado ya, si no cualquiera podria añadir la suya."""
    quien, _ = _quien(authorization)
    return rostro.alta_empieza(getattr(quien, "email", "") or "")


@app.post("/api/rostro/alta")
async def rostro_alta(body: Rostro, authorization: str = Header(default="")):
    _quien(authorization)
    try:
        return rostro.alta_termina(body.respuesta, body.apodo)
    except rostro.NoVale as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/rostro/olvidar")
async def rostro_olvidar(body: Rostro, authorization: str = Header(default="")):
    """Da de baja un telefono, o todos. Existe desde el primer dia: una llave que se da de alta y
    no de baja es una llave que no se puede cambiar, y si se pierde el movil esto es lo unico que
    cierra la puerta."""
    _quien(authorization)
    return {"quedan": rostro.olvidar(str(body.respuesta.get("id") or ""))}


@app.post("/api/rostro/pin")
async def rostro_abre_pin(body: Rostro, authorization: str = Header(default="")):
    """Abre con la cara la misma ventana que abre el PIN.

    NO rebaja la barrera: el PIN son cuatro cifras que se escriben en la calle y se miran por
    encima del hombro; esto es biometria comprobada por el chip del telefono. Lo que se exige es lo
    mismo, demostrar otra vez que eres tu antes de lo que no se deshace.
    """
    _, token = _quien(authorization)
    try:
        rostro.entrada_termina(body.respuesta)
    except rostro.NoVale as e:
        raise HTTPException(401, str(e)) from e
    hasta = clave_mod.abre_con_rostro(_huella(token))
    return {"abierto": True, "segundos": int(hasta - time.time())}


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
        token = authorization.split(" ", 1)[1]
        sesion.olvidar(token)
        # Salir cierra tambien la ventana del PIN: si no, volver a entrar con la clave heredaria el
        # permiso de publicar de la sesion anterior.
        clave_mod.cierra_pin(_huella(token))
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
    lista, avisos_sueltos, fallos = lector.pendientes()
    # Dos preguntas distintas en una respuesta: las COLAS dicen cuanto queda en total y el feed dice
    # que hacer ahora. Con solo el feed parecia que habia una cosa pendiente cuando habia 113.
    colas, fallos_colas = lector.pendiente_completo()
    return {
        "fallos": fallos + fallos_colas,
        "avisos": avisos_sueltos,
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
                          "se_puede_abrir": a.se_puede_abrir, "reversible": a.reversible,
                          "metodo": a.metodo, "cuerpo": a.cuerpo,
                          "se_puede_ejecutar": a.se_puede_ejecutar}
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


@app.get("/api/cola/{cola}")
async def api_cola(cola: str, limite: int = Query(default=25, ge=1, le=100),
                   authorization: str = Header(default="")):
    """Una cola entera, para despacharla desde aqui en vez de abrir el cockpit."""
    _quien(authorization)
    elementos, fallo, resumen = lector.elementos_de_cola(cola, limite)
    return {"cola": cola, "cuantos": len(elementos), "elementos": elementos,
            "resumen": resumen, "fallos": [fallo] if fallo else []}


@app.get("/api/colas")
async def api_colas(authorization: str = Header(default="")):
    """Cuales se pueden abrir. El front no lo adivina: lo pregunta."""
    _quien(authorization)
    cuales, fallos = lector.colas_que_se_abren()
    return {"colas": cuales, "fallos": fallos}


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


# ---------------------------------------------------------------- J4: ejecutar una accion

class Dicho(BaseModel):
    frase: str
    #: Si viene, la frase NO es una orden nueva: es la respuesta a la confirmacion de ese vale.
    #: Se manda al servidor en vez de decidirlo en el navegador para que la regla de que cuenta
    #: como un si viva en UN sitio, con sus tests, y no duplicada en JavaScript.
    vale: str = ""


class AccionPropuesta(BaseModel):
    op: str
    etiqueta: str
    url: str
    efecto: str
    coste_api: bool = False
    titulo: str = ""
    #: Para lo que no es un webhook. Por defecto GET, que es como estan hechas las 33 acciones del
    #: catalogo: cambiar el valor por defecto las habria roto todas de golpe.
    metodo: str = "GET"
    cuerpo: dict | None = None


class Pin(BaseModel):
    pin: str


class ValeDeAccion(BaseModel):
    """El vale de una ejecucion.

    Se declara AQUI y no se reutiliza el de la agenda, que vive doscientas lineas mas abajo. Con
    `from __future__ import annotations` la anotacion es un texto que FastAPI resuelve al registrar
    la ruta: si la clase todavia no existe, no falla al arrancar, se traga el modelo y trata el
    cuerpo como un parametro de la URL. El endpoint respondia 422 "field required" en produccion y
    el codigo se leia perfectamente bien. Lo encontro una prueba contra el servicio, no el import.
    """
    vale: str


def _huella(token: str) -> str:
    """Identifica la sesion sin guardar el token. La ventana del PIN va por sesion, no global: un
    navegador olvidado abierto no puede dejar publicar desde otro sitio."""
    import hashlib                                        # noqa: PLC0415
    return hashlib.sha256(token.encode()).hexdigest()[:24]


@app.post("/api/pin")
async def pin_abrir(body: Pin, authorization: str = Header(default="")):
    """Abre la ventana para lo que publica. Diez minutos y solo para esta sesion."""
    _, token = _quien(authorization)
    try:
        hasta = clave_mod.abre_con_pin(_huella(token), body.pin)
    except clave_mod.ClaveNoConfigurada as e:
        raise HTTPException(503, str(e)) from e
    except clave_mod.PinMalo as e:
        raise HTTPException(401, str(e)) from e
    return {"abierto": True, "segundos": int(hasta - time.time())}


@app.get("/api/pin")
async def pin_estado(authorization: str = Header(default="")):
    _, token = _quien(authorization)
    return {"hay_pin": clave_mod.hay_pin(), "abierto": clave_mod.pin_abierto(_huella(token))}


@app.post("/api/orden")
async def api_orden(body: Dicho, authorization: str = Header(default="")):
    """Una frase dicha en voz alta, emparejada con algo que ya esta en la pantalla.

    NO EJECUTA: deja el vale preparado y devuelve la frase que hay que decir en alto para
    confirmar. Ejecutar sigue siendo `/api/accion/confirmar`, la misma puerta de siempre y el
    mismo diario. Esto solo evita tener que buscar el boton con el dedo.

    QUE SE EMPAREJA. Solo lo que Zeno ya tenia delante en ese momento: no hay forma de nombrar
    algo que no estuviera en la pantalla. Y de eso, solo lo reversible (lo decidio el operador el
    28-sep): lo que sale al mundo sigue pidiendo el dedo y el PIN.

    Cuesta cero: el emparejado es por reglas, no por modelo.
    """
    _quien(authorization)
    if body.vale:
        # Responder a la confirmacion. Aqui NO se ejecuta: se dice si el operador ha dicho que si,
        # y quien ejecuta sigue siendo `/api/accion/confirmar`, con su vale de un solo uso y su
        # diario. Un solo sitio por el que sale algo al mundo.
        return {"estado": "si" if ordenes.dice_que_si(body.frase) else "no"}
    lista, avisos_sueltos, _ = lector.pendientes()
    # Las dos listas juntas, en la forma que espera el emparejador.
    cosas = [{"titulo": p.titulo,
              "acciones": [{"etiqueta": a.etiqueta, "op": a.op, "efecto": a.efecto,
                            "coste_api": a.coste_api, "url": a.url,
                            "reversible": a.reversible} for a in p.acciones]}
             for p in lista] + avisos_sueltos
    r = ordenes.empareja(body.frase, cosas)

    if r["estado"] == "no_es_orden":
        return {"estado": "no_es_orden"}
    if r["estado"] == "no_entiendo":
        return {"estado": "no_entiendo", "decir": "no te he entendido"}
    if r["estado"] == "nada_encaja":
        return {"estado": "nada_encaja", "decir": "no encuentro nada que se llame así"}
    if r["estado"] == "varias":
        cuales = ", o ".join(x[:60] for x in r["cuales"])
        return {"estado": "varias", "decir": f"hay varias: {cuales}. ¿Cuál?"}
    if r["estado"] == "no_por_voz":
        return {"estado": "no_por_voz", "decir": r["por_que"]}

    a, cosa = r["accion"], r["cosa"]
    try:
        vale = ejecutor.propone(a.get("op"), a.get("etiqueta"), a.get("url"), a.get("efecto"),
                                bool(a.get("coste_api")), cosa.get("titulo", ""),
                                a.get("metodo", "GET"), a.get("cuerpo"))
    except ejecutor.NoSePuede as e:
        return {"estado": "no_se_puede", "decir": str(e)}
    return {"estado": "vale", "vale": vale["vale"],
            "etiqueta": a.get("etiqueta"), "titulo": cosa.get("titulo", ""),
            # La frase se dice TAL CUAL en alto, asi que nombra lo que se va a tocar. "¿Confirmas?"
            # a secas obliga a recordar de que se hablaba, y hablando no hay pantalla que mirar.
            "decir": f"{a.get('etiqueta')}: {cosa.get('titulo', '')}. ¿Lo hago?"}


@app.post("/api/accion/proponer")
async def accion_proponer(body: AccionPropuesta, authorization: str = Header(default="")):
    """Prepara la ejecucion y devuelve un vale. NO llama a nadie todavia."""
    _quien(authorization)
    try:
        return ejecutor.propone(body.op, body.etiqueta, body.url, body.efecto,
                                body.coste_api, body.titulo, body.metodo, body.cuerpo)
    except ejecutor.NoSePuede as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/accion/confirmar")
async def accion_confirmar(body: ValeDeAccion, authorization: str = Header(default="")):
    """LO UNICO que ejecuta. Cierra J4, y es lo que puede publicar en nombre del operador."""
    _, token = _quien(authorization)
    try:
        return ejecutor.confirma(body.vale, clave_mod.pin_abierto(_huella(token)))
    except ejecutor.HaceFaltaPin as e:
        # 428 y no 401: la sesion es buena, lo que falta es el PIN. Con 401 el front borraria el
        # token y echaria al operador fuera en mitad de una aprobacion.
        raise HTTPException(428, str(e)) from e
    except ejecutor.NoSePuede as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/hecho")
async def api_hecho(cuantos: int = Query(default=30, ge=1, le=200),
                    authorization: str = Header(default="")):
    """Lo que Zeno ha hecho, del mas reciente al mas viejo.

    Contesta a la pregunta que aparecio el dia que Zeno empezo a publicar: si algo salio desde aqui
    o desde otro sitio. Y los intentos de los que no se supo el resultado salen marcados, porque son
    justo los que hay que ir a mirar.
    """
    _quien(authorization)
    return {"hecho": diario.lee(cuantos)}


# ---------------------------------------------------------------- la documentación

@app.get("/api/buscar")
async def buscar(q: str = Query(..., min_length=2), authorization: str = Header(default="")):
    """El corpus. `modo` dice si respondió por significado o degradado a texto: el front lo enseña,
    porque contestar "no hay nada" con el servicio de embeddings caído es mentir con seguridad."""
    _quien(authorization)
    resultados, modo, fallos = lector.documentacion(q)
    return {"resultados": resultados, "modo": modo, "fallos": fallos}


# ---------------------------------------------------------------- el chat (apagado de serie)

class Turno(BaseModel):
    de: str
    texto: str


class Pregunta(BaseModel):
    texto: str
    #: Lo hablado antes en esta conversacion, tal como esta en pantalla. Sigue mandandolo el front
    #: porque es la verdad de lo que el operador esta viendo. Desde el 2026-09-28 tambien se guarda
    #: en el servidor: la razon por la que no se guardaba ("la conversacion se acaba al cerrar la
    #: aplicacion") era precisamente el problema, no el motivo.
    turnos: list[Turno] = []


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

    # "RECUERDA QUE..." NO GASTA API. Se reconoce con reglas, se guarda tal cual lo dijo y se
    # contesta desde aquí. Pasarlo por el modelo costaría dinero para que parafrasease una orden
    # que ya está clara, y encima con el riesgo de que guardase su versión en vez de la suya.
    esto = memoria.es_para_recordar(pregunta)
    if esto:
        apunte = memoria.apunta(esto, origen="dicho")
        memoria.guarda_turno("tu", pregunta)
        respuesta = f"Apuntado: {esto}"
        memoria.guarda_turno("zeno", respuesta)
        return {"respuesta": respuesta, "modelo": "(sin modelo)", "coste_usd": 0.0,
                "apuntado": apunte,
                "preguntas_hoy": chat_mod.preguntas_hoy(), "tope_diario": chat_mod.TOPE_DIARIO}

    lista, _, fallos = lector.pendientes()
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
    # Los turnos de la PANTALLA mandan: es lo que el operador esta viendo. Solo cuando no manda
    # ninguno (acaba de abrir la aplicacion) se recupera lo hablado la ultima vez, que es justo el
    # caso que hacia que Zeno se olvidara de todo entre sesiones.
    turnos = [t.model_dump() for t in body.turnos] or memoria.hilo()
    try:
        salida = chat_mod.responde(pregunta, lista, colas, fallos + fallos_colas,
                                   documentos, estado, ventas, turnos=turnos,
                                   recuerdos=memoria.para_el_contexto(),
                                   hechos=diario.lee(12))
    except chat_mod.TopeAlcanzado as e:
        raise HTTPException(429, f"Tope diario de preguntas alcanzado ({e})") from e
    except chat_mod.SinClaveDeIA as e:
        raise HTTPException(503, str(e)) from e
    # SOLO SE GUARDA LO QUE SALIO BIEN. Una pregunta cuya respuesta fallo no deja media
    # conversacion escrita: al volver manana, el hilo tendria un turno tuyo sin contestar y el
    # modelo lo leeria como algo que quedo pendiente.
    memoria.guarda_turno("tu", pregunta)
    memoria.guarda_turno("zeno", salida.get("respuesta", ""))
    return salida


# ---------------------------------------------------------------- lo que Zeno recuerda

class Apunte(BaseModel):
    texto: str


@app.get("/api/memoria")
async def api_memoria(authorization: str = Header(default="")):
    """Todo lo que Zeno recuerda, para poder mirarlo y borrarlo.

    ESTA PANTALLA ES LA CONDICION para que la memoria exista. Una memoria que no se puede ver
    acaba repitiendo como cierto algo que caduco hace semanas, y el operador no tiene forma de
    saber de donde salio. Por eso cada apunte lleva su fecha y su origen.
    """
    _quien(authorization)
    return {"apuntes": memoria.apuntes(), "turnos": len(memoria.hilo(999)),
            "ultima_vez": memoria.cuando_fue_lo_ultimo()}


@app.post("/api/memoria")
async def api_memoria_apunta(body: Apunte, authorization: str = Header(default="")):
    """Apunta algo a mano, sin pasar por el chat. No gasta nada."""
    _quien(authorization)
    texto = (body.texto or "").strip()
    if len(texto) < 2:
        raise HTTPException(422, "escribe qué quieres que recuerde")
    return {"apunte": memoria.apunta(texto, origen="dicho")}


@app.delete("/api/memoria/{ident}")
async def api_memoria_olvida(ident: str, authorization: str = Header(default="")):
    """Olvida un apunte. Se tacha, no se reescribe el fichero."""
    _quien(authorization)
    memoria.olvida(ident)
    return {"olvidado": ident}


@app.delete("/api/hilo")
async def api_hilo_borra(authorization: str = Header(default="")):
    """Corta la conversacion guardada y empieza de cero. No toca los apuntes."""
    _quien(authorization)
    memoria.olvida_el_hilo()
    return {"ok": True}


@app.get("/api/hilo")
async def api_hilo(authorization: str = Header(default="")):
    """Lo ultimo que se hablo, para repintarlo al abrir la aplicacion."""
    _quien(authorization)
    return {"turnos": memoria.hilo(), "ultima_vez": memoria.cuando_fue_lo_ultimo()}


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
    for negocio, direccion in google.CUENTAS.items():
        ident, _ = google._cliente(negocio)
        cuentas.append({"negocio": negocio, "cuenta": direccion,
                        "conectada": negocio in conectadas,
                        # El buzon REAL al que apunta. Si dos cuentas traen el mismo, una es alias
                        # de la otra y el front tiene que decirlo en vez de fingir que son dos.
                        "buzon": conectadas.get(negocio, {}).get("buzon", ""),
                        # Sin cliente configurado el botón no puede funcionar: se dice, en vez de
                        # dejar que el operador pulse y se coma un error de Google.
                        "configurada": bool(ident),
                        "permisos": conectadas.get(negocio, {}).get("permisos", []),
                        # LO QUE FALTA POR CONCEDER. Zeno sabe que permisos pidio y cuales le
                        # dieron: cuando se abre un tramo nuevo, la cuenta sigue conectada con los
                        # permisos VIEJOS y la funcion nueva falla sin explicar por que. Decirlo
                        # aqui convierte "no funciona" en "reconecta y ya".
                        "faltan": (google.faltan(conectadas[negocio].get("permisos", []))
                                   if negocio in conectadas else [])})
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


class Cambio(BaseModel):
    id: str
    desde: str = ""
    minutos: int | None = None


class ValeDeCita(BaseModel):
    vale: str


@app.post("/api/agenda/mover")
async def agenda_mover(body: Cambio, authorization: str = Header(default="")):
    """Prepara mover una cita. NO la mueve."""
    _quien(authorization)
    try:
        return citas.propone_cambio(_cual_buzon(), body.id, body.desde, body.minutos)
    except citas.NoSePuede as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/agenda/cancelar")
async def agenda_cancelar(body: Cambio, authorization: str = Header(default="")):
    """Prepara cancelar una cita. NO la cancela."""
    _quien(authorization)
    try:
        return citas.propone_baja(_cual_buzon(), body.id)
    except citas.NoSePuede as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/agenda/cambio/confirmar")
async def agenda_cambio_confirmar(body: ValeDeCita, authorization: str = Header(default="")):
    """Mueve o cancela de verdad. Con invitados hace falta el PIN: les llega un correo."""
    _, token = _quien(authorization)
    try:
        return citas.confirma_cambio(body.vale, clave_mod.pin_abierto(_huella(token)))
    except citas.NoSePuede as e:
        # 428 cuando lo que falta es el PIN, igual que al ejecutar una accion: con 401 el front
        # borraria el token y echaria al operador fuera en mitad de una cancelacion.
        raise HTTPException(428 if "PIN" in str(e) else 409, str(e)) from e
    except google.NoAutorizado as e:
        raise HTTPException(503, str(e)) from e


class Redaccion(BaseModel):
    id: str
    intencion: str = ""


class Borrador(BaseModel):
    id: str
    texto: str


class ValeDeBorrador(BaseModel):
    vale: str


@app.post("/api/correo/redactar")
async def correo_redactar(body: Redaccion, authorization: str = Header(default="")):
    """Propone un texto de respuesta. Cuesta una llamada y no escribe nada en Gmail."""
    _quien(authorization)
    if not CHAT_ACTIVO:
        raise HTTPException(501, "Redactar gasta API y todavia no esta encendido")
    try:
        original = correo.lee_entero(_cual_buzon(), body.id)
    except google.NoAutorizado as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:                                # noqa: BLE001
        raise HTTPException(422, f"no encuentro ese correo ({type(e).__name__})") from e
    try:
        return chat_mod.redacta_respuesta(original, body.intencion)
    except chat_mod.TopeAlcanzado as e:
        raise HTTPException(429, str(e)) from e
    except chat_mod.SinClaveDeIA as e:
        raise HTTPException(503, str(e)) from e


@app.post("/api/correo/borrador")
async def correo_borrador(body: Borrador, authorization: str = Header(default="")):
    """Prepara el borrador. NO lo guarda todavia."""
    _quien(authorization)
    try:
        return correo.prepara(_cual_buzon(), body.id, body.texto)
    except correo.NoSePuede as e:
        raise HTTPException(422, str(e)) from e
    except google.NoAutorizado as e:
        raise HTTPException(503, str(e)) from e


@app.post("/api/correo/borrador/confirmar")
async def correo_borrador_confirmar(body: ValeDeBorrador, authorization: str = Header(default="")):
    """Guarda el borrador en Gmail. NO envia: no hay ningun camino en Zeno que envie correo."""
    _quien(authorization)
    try:
        return correo.guarda(body.vale)
    except correo.NoSePuede as e:
        raise HTTPException(409, str(e)) from e
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
