# -*- coding: utf-8 -*-
"""Zeno leyendo: junta las dos colas y el estado de los dos negocios. NO escribe nada.

POR QUE ASI. Zeno vive fuera del cockpit y de Xrise, y no es dueño de ninguna cola: las LEE. Si
guardase su propia copia habria tres sitios diciendo cosas distintas del mismo hecho, que es el
patron que ya ha costado tres incidentes en este ecosistema.

COMO ENTRA. Con una clave de solo lectura por sistema (`X-Zeno-Key`), distinta de la de n8n. En Xrise
ademas manda `X-Zeno-Org`, y esa clave solo abre las organizaciones declaradas en el servidor: Xrise
es multi-tenant y se vende, asi que no puede leer los datos de un cliente real.

LO QUE APORTA SOBRE MIRAR LAS DOS PANTALLAS. Cruza cada aviso con el CATALOGO de J1, asi que puede
decir de cada cosa pendiente si al aprobarla SALE AL MUNDO y no vuelve, si solo cambia un estado, o si
gasta una llamada de pago. Eso no esta en ninguna de las dos colas: ninguna lo sabe de si misma, y
menos de la otra.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalogo as C                                  # noqa: E402

#: Donde vive cada API. Por defecto se habla con la red interna del servidor; fuera de ahi, con los
#: dominios publicos. Se puede sobreescribir para probar contra otro sitio.
COCKPIT = os.environ.get("ZENO_COCKPIT_URL", "https://cockpit.zenvrax.com/api")
XRISE = os.environ.get("ZENO_XRISE_URL", "https://xrise.zenvrax.com/api")
CLAVE = os.environ.get("ZENO_READ_KEY", "")
ORG = os.environ.get("ZENO_ORG", "gutlyn")

NEGOCIO = {"cockpit": "Zenvrax", "xrise": "GutLyn"}


class SinClave(RuntimeError):
    """Zeno no tiene con que leer. Se dice en vez de devolver listas vacias, que se leerian como
    "no hay nada pendiente"."""


@dataclass
class Accion:
    """Una accion de un aviso concreto: su contrato y su destino real."""
    etiqueta: str
    op: str | None
    efecto: str | None
    coste_api: bool
    url: str = ""

    @property
    def se_puede_abrir(self) -> bool:
        """Solo lo que ABRE algo y trae una direccion de verdad. Lo que ejecuta no se pulsa todavia:
        eso es J4 y pasa por el contrato, no por un enlace."""
        return self.efecto == C.ABRE and self.url.startswith("http")


@dataclass
class Pendiente:
    """Algo que espera una decision del operador, con lo que hace falta saber para decidir."""
    negocio: str
    titulo: str
    cuerpo: str
    acciones: list = field(default_factory=list)   # list[Accion]
    fuente: str = ""

    @property
    def publica_algo(self) -> bool:
        return any(a.efecto == C.PUBLICA for a in self.acciones)

    @property
    def cuesta_dinero(self) -> bool:
        return any(a.coste_api for a in self.acciones)

    @property
    def sin_contrato(self) -> int:
        """Acciones que el catalogo no reconoce. No se ocultan: se cuentan y se dicen."""
        return sum(1 for a in self.acciones if a.op is None)


def _pide(base: str, ruta: str, cabeceras: dict | None = None) -> dict | list:
    if not CLAVE:
        raise SinClave("falta ZENO_READ_KEY en el entorno: Zeno no puede leer nada")
    cab = {"X-Zeno-Key": CLAVE, "Accept": "application/json"}
    cab.update(cabeceras or {})
    req = urllib.request.Request(base.rstrip("/") + ruta, headers=cab, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or "{}")


def _seguro(base: str, ruta: str, cabeceras: dict | None = None):
    """Como `_pide`, pero devuelve el error en vez de propagarlo.

    Un sistema caido no puede dejar sin respuesta al otro: si el cockpit no contesta, lo de GutLyn
    sigue siendo cierto y hay que poder verlo. Lo que NO se hace es disimular la caida: el error
    viaja y se imprime, porque una lista corta sin aviso se lee como "hay poco pendiente".
    """
    try:
        return _pide(base, ruta, cabeceras), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} en {ruta}"
    except Exception as e:                                       # noqa: BLE001
        return None, f"{type(e).__name__} en {ruta}"


def _indice_del_catalogo() -> dict:
    """Las acciones del catalogo indexadas por (sistema, etiqueta), que es lo que trae un aviso.

    La cola manda la etiqueta que ve el operador, no el `op`: es lo unico comun entre lo que viaja en
    el aviso y lo que declara el catalogo.
    """
    fuera = {}
    for a in C.catalogo():
        fuera[(a.sistema, (a.etiqueta or "").strip())] = a
    return fuera


def _acciones(sistema: str, brutas: list, indice: dict) -> list:
    """Cada accion del aviso cruzada con su contrato, CONSERVANDO su url real.

    La url del catalogo lleva la plantilla (`.../preview?id={pid}`) porque se saca del codigo. La del
    AVISO trae el identificador ya puesto. Sin ella, "Ver preview" no puede abrir nada: era un
    `<span>` con texto, y el operador lo dijo a la primera: *"ver preview no funciona"*.

    O sea: el catalogo dice QUE es la accion, el aviso dice DONDE.
    """
    fuera = []
    for a in brutas or []:
        etiqueta = (a.get("label") or "").strip()
        ficha = indice.get((sistema, etiqueta))
        fuera.append(Accion(
            etiqueta=etiqueta,
            op=ficha.op if ficha else None,
            efecto=ficha.efecto if ficha else None,
            coste_api=bool(ficha and ficha.coste_api),
            url=a.get("url") or "",
        ))
    return fuera


def pendientes() -> tuple[list[Pendiente], list[str]]:
    """Todo lo que espera una decision, de los dos negocios. Devuelve (lista, avisos de fallo)."""
    indice = _indice_del_catalogo()
    fuera, fallos = [], []

    datos, err = _seguro(COCKPIT, "/notifications?limit=60")
    if err:
        fallos.append(f"Zenvrax (cockpit): {err}")
    else:
        for n in (datos if isinstance(datos, list) else datos.get("items", [])):
            acc = _acciones("cockpit", n.get("actions"), indice)
            if not acc:
                continue                       # un aviso sin botones no espera una decision
            fuera.append(Pendiente(negocio=NEGOCIO["cockpit"], titulo=n.get("title") or "?",
                                   cuerpo=(n.get("body") or "").strip(), acciones=acc,
                                   fuente="cockpit"))

    datos, err = _seguro(XRISE, "/dashboard/notifications", {"X-Zeno-Org": ORG})
    if err:
        fallos.append(f"GutLyn (Xrise): {err}")
    else:
        for n in (datos if isinstance(datos, list) else datos.get("items", [])):
            acc = _acciones("xrise", n.get("actions"), indice)
            if not acc:
                continue
            fuera.append(Pendiente(negocio=NEGOCIO["xrise"], titulo=n.get("title") or "?",
                                   cuerpo=(n.get("body") or "").strip(), acciones=acc,
                                   fuente="xrise"))

    # Primero lo que al aprobarlo sale al mundo: es lo que no se puede deshacer.
    fuera.sort(key=lambda p: (not p.publica_algo, p.negocio, p.titulo))
    return fuera, fallos


def estado() -> tuple[dict, list[str]]:
    """Como van los dos negocios, cada uno de su propia fuente."""
    fuera, fallos = {}, []
    for etiqueta, base, ruta, cab in (
            ("zenvrax", COCKPIT, "/aios/overview", None),
            ("plan_del_dia", COCKPIT, "/autopilot/plan", None),
            ("gutlyn", XRISE, "/dashboard/executive", {"X-Zeno-Org": ORG})):
        datos, err = _seguro(base, ruta, cab)
        if err:
            fallos.append(f"{etiqueta}: {err}")
        else:
            fuera[etiqueta] = datos
    return fuera, fallos


def documentacion(consulta: str) -> tuple[list, str, list[str]]:
    """Que dice el corpus sobre algo. Devuelve (resultados, modo, fallos).

    El `modo` importa y se ensena: "significado" es el recall semantico del Brain y "texto" es la
    caida a un LIKE. Si Zeno contesta "el corpus no dice nada" cuando en realidad el servicio de
    embeddings esta caido, esta mintiendo con cara de certeza.
    """
    datos, err = _seguro(COCKPIT, "/search/conocimiento?q=" + urllib.parse.quote(consulta))
    if err:
        return [], "no disponible", [f"conocimiento: {err}"]
    return datos.get("conocimiento") or [], datos.get("conocimiento_modo") or "?", []


def pendiente_completo() -> tuple[list[dict], list[str]]:
    """TODO lo que espera una decision, por cola, de los dos negocios.

    POR QUE NO VALE `pendientes()`. Aquella lee los FEEDS de aviso, que estan hechos para dar una
    cosa al dia: la de Xrise literalmente hace `LIMIT 1` y solo mira lo vencido. El operador lo vio
    en cuanto abrio Zeno: *"no da todo lo pendiente en cada plataforma"*. Medido ese dia: 113
    pendientes de verdad (82 en Zenvrax, 31 en GutLyn) y el feed enseñaba UNA.

    Las dos siguen haciendo falta y no se sustituyen: `pendientes()` dice QUE HACER AHORA, con sus
    botones y su contrato; esta dice CUANTO QUEDA. Son preguntas distintas.
    """
    colas, fallos = [], []
    for etiqueta, base, ruta, cab in (
            ("Zenvrax", COCKPIT, "/aios/pendiente-todo", None),
            ("GutLyn", XRISE, "/dashboard/pendiente-todo", {"X-Zeno-Org": ORG})):
        datos, err = _seguro(base, ruta, cab)
        if err:
            fallos.append(f"{etiqueta}: {err}")
            continue
        for c in datos.get("colas") or []:
            colas.append({**c, "negocio": datos.get("negocio", etiqueta)})
        # Los fallos parciales del otro lado (por ejemplo, que no se pueda contar el organico)
        # viajan tal cual: un total corto sin aviso se lee como "hay poco pendiente".
        fallos.extend(datos.get("fallos") or [])
    colas.sort(key=lambda c: (-c["cuantos"], c["negocio"]))
    return colas, fallos
