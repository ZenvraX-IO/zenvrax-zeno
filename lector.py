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


def ventas_gutlyn() -> tuple[dict, list[str]]:
    """Las cifras de venta de GutLyn, de Xrise, que es donde vive el ecommerce.

    POR QUE EXISTE. El operador le pregunto al chat *"situacion actual de ventas de GutLyn"* y
    contesto que no tenia el dato. Tenia razon en quejarse: Zeno leia lo pendiente y los avisos,
    pero no las VENTAS, que estan en `/dashboard/overview` y `/dashboard/pnl` de Xrise. Un asistente
    que no puede contestar como va el negocio no es un asistente, es una bandeja.
    """
    fuera, fallos = {}, []
    for etiqueta, ruta in (("resumen", "/dashboard/overview"), ("perdidas_y_ganancias", "/dashboard/pnl")):
        datos, err = _seguro(XRISE, ruta, {"X-Zeno-Org": ORG})
        if err:
            fallos.append(f"ventas de GutLyn ({etiqueta}): {err}")
        else:
            fuera[etiqueta] = datos
    return fuera, fallos


# ---------------------------------------------------------------- los dos negocios a la par

def _dinero(v) -> str:
    """Una cifra de dinero como se lee, no como la guarda la base."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "sin dato"
    return f"${n:,.0f}".replace(",", ".") if abs(n) >= 1000 else f"${n:,.2f}".rstrip("0").rstrip(".")


def _numero(v, sufijo: str = "") -> str:
    if v is None:
        return "sin dato"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    entero = f"{int(n):,}".replace(",", ".") if n == int(n) else f"{n:,.1f}".replace(",", ".")
    return entero + sufijo


def negocios() -> tuple[list[dict], list[str]]:
    """Los dos negocios uno al lado del otro: como van y que espera tu OK en cada uno.

    NO HAY NINGUNA FUENTE NUEVA. Todo esto ya lo leia Zeno para contestar en el chat: los KPI de
    Zenvrax salen del cockpit, las cifras de GutLyn de Xrise y lo pendiente de las dos colas. Lo que
    faltaba era la pantalla: para saber como iba un negocio habia que preguntarselo al chat, o sea
    pagar una llamada a la API y esperar, para leer numeros que ya estaban ahi.

    Cada negocio trae sus fallos DENTRO de su tarjeta y no en un monton comun: si Xrise no contesta,
    lo que no se sabe es como va GutLyn, y esa distincion se pierde en una lista de errores suelta.
    """
    fallos: list[str] = []
    est, f1 = estado()
    ventas, f2 = ventas_gutlyn()
    colas, f3 = pendiente_completo()
    fallos += f1 + f2 + f3

    # Lo pendiente se reparte por negocio. El nombre viene de las colas tal cual, asi que se compara
    # en minusculas: "GutLyn" y "gutlyn" son el mismo sitio.
    por_negocio: dict[str, list[dict]] = {}
    for c in colas:
        por_negocio.setdefault(str(c.get("negocio", "")).lower(), []).append(c)

    def bloque(ident, nombre, sub, kpis, fuente):
        mias = por_negocio.get(ident, [])
        return {"id": ident, "nombre": nombre, "sub": sub, "fuente": fuente, "kpis": kpis,
                "pendiente": sum(c.get("cuantos", 0) for c in mias),
                "colas": [{"titulo": c.get("titulo"), "cuantos": c.get("cuantos"),
                           "donde": c.get("donde")} for c in mias]}

    # ZENVRAX. El cockpit ya devuelve los KPI con su alerta y su enlace: se pasan tal cual en vez de
    # recalcularlos aqui, que seria el mismo dato en dos sitios y con dos verdades.
    kpis_z = []
    for n in ((est.get("zenvrax") or {}).get("negocios") or []):
        if str(n.get("id", "")).lower() == "zenvrax":
            kpis_z = n.get("kpis") or []
    fuera = [bloque("zenvrax", "Zenvrax IO", "consultoría", kpis_z, "cockpit")]

    # GUTLYN. El cockpit devuelve la ficha del negocio sin KPI (los lleva Xrise), asi que se arman
    # desde las ventas. Un cero es un cero y se escribe: "sin dato" solo cuando de verdad falta.
    r = (ventas.get("resumen") or {})
    kpis_g = [
        {"k": "Ingresos 30d", "v": _dinero(r.get("revenue"))},
        {"k": "Pedidos", "v": _numero(r.get("orders"))},
        {"k": "Beneficio neto", "v": _dinero(r.get("net_profit")),
         "alerta": "bad" if (r.get("net_profit") or 0) < 0 else None},
        {"k": "Margen", "v": _numero(r.get("net_margin_pct"), "%")},
        {"k": "Publicidad", "v": _dinero(r.get("ad_spend"))},
        {"k": "TACoS", "v": _numero(r.get("tacos_pct"), "%")},
        {"k": "Ticket medio", "v": _dinero(r.get("avg_order_value"))},
        {"k": "Devoluciones", "v": _dinero(r.get("returns_amount"))},
    ]
    fuera.append(bloque("gutlyn", "GutLyn+", "ecommerce", kpis_g, "Xrise"))

    # Cada fallo se pega al negocio del que habla: "no se sabe como va GutLyn" es un dato distinto
    # de "hay un error por ahi".
    for b in fuera:
        b["fallos"] = [f for f in fallos if b["id"] in f.lower() or b["nombre"].lower() in f.lower()]
    sueltos = [f for f in fallos if not any(f in b["fallos"] for b in fuera)]
    return fuera, sueltos


# ---------------------------------------------------------------- lo primero de la mañana

def plan_del_dia() -> tuple[dict, list[str]]:
    """Lo que hay que hacer hoy: el foco, lo urgente y cuanto queda.

    Sale del `/autopilot/plan` del cockpit, que YA decide que es lo primero y que es urgente. Zeno
    no reordena ni reinventa esa prioridad: si la calculara aqui a su manera, habria dos criterios
    distintos para lo mismo y el operador no sabria cual esta mirando.

    Lo que NO se trae, y se dice para que no se busque: el `done_today` del cockpit son entradas de
    acceso a la aplicacion (logins, segundos factores), no trabajo terminado. Enseñarlo como "lo
    hecho hoy" seria contar 13 cosas hechas cuando no se ha hecho ninguna.
    """
    datos, err = _seguro(COCKPIT, "/autopilot/plan")
    if err:
        return {}, [f"el plan del dia: {err}"]

    def limpia(t):
        """El titulo, sin el emoji de delante ni la raya larga.

        Los titulos del cockpit vienen como "<emoji> Tarea - La landing...". El emoji es decoracion
        de otra pantalla y aqui solo roba sitio; la raya larga esta prohibida en todo lo que sale de
        esta casa, y colarse por un dato leido cuenta igual.

        EL ORDEN IMPORTA: la raya se sustituye ANTES de quitar lo que no es texto. Al reves, el
        filtro se la comia y dejaba dos espacios en medio de la frase.
        """
        t = str(t or "").strip()
        t = t.replace("—", ", ").replace("–", ", ")
        # Se conserva letra, numero, espacio y puntuacion normal: eso deja fuera los emoji y los
        # selectores de variante que los acompañan, sin tener que listarlos uno a uno.
        t = "".join(c for c in t if c.isalnum() or c.isspace() or c in ",.;:()[]'\"!?+-/%$&@#")
        t = " ".join(t.split())
        # "Tarea - La landing" deja "Tarea , La landing": la raya venia con espacio delante. Es el
        # mismo detalle que ya se arreglo en las respuestas del chat.
        for signo in (",", ".", ";", ":"):
            t = t.replace(" " + signo, signo)
        return t.strip(" ,-")

    plan = datos.get("plan") or []
    urgentes = [p for p in plan if p.get("severity") == "urgent"]
    cuentas = datos.get("counts") or {}
    foco = datos.get("focus") or {}
    return {
        "foco": {"titulo": limpia(foco.get("title")), "tipo": foco.get("kind"),
                 "severidad": foco.get("severity"), "url": foco.get("url"),
                 "cuerpo": (foco.get("body") or "")[:300]} if foco.get("title") else None,
        "urgentes": [{"titulo": limpia(p.get("title")), "tipo": p.get("kind"),
                      "url": p.get("url")} for p in urgentes],
        # El resto del plan viaja para que el resumen escrito lo tenga en cuenta, aunque la pantalla
        # solo enseñe lo urgente: decidir bien necesita ver todo, enseñar bien necesita ver poco.
        "resto": [{"titulo": limpia(p.get("title")), "tipo": p.get("kind"),
                   "severidad": p.get("severity"), "url": p.get("url")}
                  for p in plan if p.get("severity") != "urgent"],
        "cuantas_pendientes": cuentas.get("pending"),
        "cuantas_urgentes": cuentas.get("urgent", len(urgentes)),
    }, []


def alertas() -> tuple[list[dict], list[str]]:
    """Lo que esta en ambar o rojo en los dos sistemas, ya junto.

    Solo lo que NO esta bien: una lista de ocho semaforos en verde no es informacion, es ruido que
    entrena a no mirar. Hoy sale una sola cosa de Xrise, los signups de waitlist sin contactar, y
    eso es exactamente lo que se quiere ver.
    """
    fuera, fallos = [], []
    est, f1 = _seguro(COCKPIT, "/aios/overview")
    if f1:
        fallos.append(f"los avisos de Zenvrax: {f1}")
    else:
        for a in (est.get("agenda") or []):
            if a.get("sev") in ("warn", "bad"):
                fuera.append({"negocio": a.get("negocio") or "Zenvrax IO",
                              "texto": a.get("texto"), "grave": a.get("sev") == "bad",
                              "donde": a.get("to")})
    xr, f2 = _seguro(XRISE, "/dashboard/executive", {"X-Zeno-Org": ORG})
    if f2:
        fallos.append(f"los avisos de GutLyn: {f2}")
    else:
        for a in (xr.get("alerts") or []):
            if a.get("tone") in ("warn", "bad"):
                fuera.append({"negocio": "GutLyn+",
                              "texto": f"{a.get('label')}: {a.get('value')}",
                              "grave": a.get("tone") == "bad", "donde": a.get("link")})
    return fuera, fallos
