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
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import lector                                    # noqa: E402
from servicio import chat as chat_mod, sesion    # noqa: E402

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
