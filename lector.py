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
import re
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

#: DONDE SE ABREN LAS COSAS, que NO es de donde se leen. Por dentro Zeno habla con
#: `http://cockpit-api:8802`, una direccion de la red de Docker que un navegador no puede abrir; y
#: los avisos traen la ruta RELATIVA ("/ops/tareas"). Puesta tal cual en un enlace, el navegador la
#: resuelve contra zeno.zenvrax.com, cae en la propia aplicacion y no pasa nada: el operador
#: pulsaba y no iba a ningun sitio.
WEB = {
    "cockpit": os.environ.get("ZENO_COCKPIT_WEB", "https://cockpit.zenvrax.com"),
    "xrise": os.environ.get("ZENO_XRISE_WEB", "https://xrise.zenvrax.com"),
}


def enlaza(sistema: str, url: str) -> str:
    """Una direccion que un navegador pueda abrir.

    Lo que ya es absoluto se deja intacto: las acciones de las colas son webhooks de n8n con su
    dominio puesto, y prefijarlas las romperia.
    """
    url = (url or "").strip()
    if not url or url.startswith(("http://", "https://", "mailto:")):
        return url
    return WEB.get(sistema, "").rstrip("/") + "/" + url.lstrip("/")


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
    #: Si se puede deshacer. Viene del catalogo y sube hasta el front porque la VOZ lo necesita:
    #: por voz solo se ejecuta lo que se deshace, y eso no se puede decidir sin este dato.
    reversible: bool = False
    #: Con que verbo y que cuerpo se dispara. Las acciones que solo abren no lo usan.
    metodo: str = "GET"
    cuerpo: dict | None = None
    #: Si Zeno puede dispararla el, o hay que abrir el sistema. Lo dice QUIEN tiene la puerta.
    se_puede_ejecutar: bool = True

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


def sin_adornos(t: str) -> str:
    """Un texto sin emoji y sin raya larga.

    Vive aqui, fuera de `plan_del_dia`, porque hace falta en tres sitios: el foco, lo urgente y las
    etiquetas de las acciones ("Ver preview" llega como "<emoji> Ver preview"). Cuando la misma
    limpieza se copia en tres sitios, se arregla en uno y se olvida en los otros dos.

    EL ORDEN IMPORTA: la raya se sustituye ANTES de quitar lo que no es texto. Al reves, el filtro
    se la come y deja dos espacios en medio de la frase.
    """
    t = str(t or "").strip()
    t = t.replace("—", ", ").replace("–", ", ")
    t = "".join(c for c in t if c.isalnum() or c.isspace() or c in ",.;:()[]'\"!?+-/%$&@#")
    t = " ".join(t.split())
    for signo in (",", ".", ";", ":"):
        t = t.replace(" " + signo, signo)
    return t.strip(" ,-")


def _huella_destino(destino: str) -> str:
    """El destino sin los huecos, para poder comparar la ruta de un aviso con la del catalogo.

    El catalogo guarda la plantilla (`/marketing/topics/{pid}`) y el aviso trae el identificador
    ya puesto (`/marketing/topics/a7ea...`). Se quedan los tramos FIJOS, que son los que
    identifican la accion.
    """
    trozos = []
    for x in re.split(r"[/?&=]", (destino or "").strip()):
        x = x.strip()
        if not x or x.startswith("{") or re.fullmatch(r"[0-9a-fA-F-]{8,}", x):
            continue
        trozos.append(x.lower())
    return "/".join(trozos)


def _indice_del_catalogo() -> dict:
    """Las acciones del catalogo, indexadas por (sistema, etiqueta) Y por (sistema, etiqueta, ruta).

    POR QUE LAS DOS CLAVES. Durante meses se indexo SOLO por (sistema, etiqueta), y eso basta
    mientras dos acciones no se llamen igual. Medido el 28-sep: hay CINCO pares que si
    ("Marcar publicado", "Ver preview", "Aprobar y publicar", "Regenerar", "Ya le he
    contestado"), y con la clave corta se cruzaba con el primero que cayera. O sea un boton podia
    ejecutarse con el contrato de otro, y el contrato es lo que dice si algo publica o si se
    deshace.

    Se probo en carne propia: al ponerle el mismo nombre a los dos botones de cerrar una
    respuesta, el que escondia el aviso paso a anunciarse como el que avanza el arco.
    """
    fuera = {}
    for a in C.catalogo():
        etiqueta = (a.etiqueta or "").strip()
        fuera[(a.sistema, etiqueta)] = a        # se conserva: la mayoria son unicas
        fuera[(a.sistema, etiqueta, _huella_destino(a.destino))] = a
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
        # El contrato se busca con la etiqueta CRUDA: es la clave del catalogo, que se recolecto
        # del codigo tal cual. Limpiarla antes rompe la busqueda y la accion se queda sin contrato,
        # o sea sin poder ejecutarse. Se limpia DESPUES, solo para enseñarla.
        # Primero con la RUTA, que desambigua cuando dos acciones se llaman igual; si no cuadra,
        # se cae a la etiqueta sola, que es como funcionaba antes y cubre a la mayoria.
        destino = (a.get("url") or (a.get("patch") or a.get("call") or {}).get("path") or "")
        ficha = (indice.get((sistema, etiqueta, _huella_destino(destino)))
                 or indice.get((sistema, etiqueta)))
        efecto = ficha.efecto if ficha else None
        # Lo que solo ABRE una pantalla lleva ruta relativa del cockpit ("/marketing/x?open=...").
        # Sin prefijar, el navegador la resuelve contra zeno.zenvrax.com y da un 404: el boton
        # existe, se pulsa y no lleva a ningun sitio. Ya paso con el foco del dia.
        url = a.get("url") or ""
        metodo, cuerpo = "GET", None
        if efecto == C.ABRE:
            url = enlaza(sistema, url)
        elif not url:
            # Las acciones que EJECUTAN algo en la API del cockpit no traen `url`: traen
            # `patch`/`call` con la ruta relativa, el verbo y el cuerpo, porque quien las dispara
            # normalmente es el front del cockpit, que ya sabe contra que API habla. Zeno no, asi
            # que la direccion se compone aqui. Sin esto el ejecutor las rechazaba con "esa
            # direccion no es de ninguno de los sistemas de casa" y eran botones muertos.
            manda = a.get("patch") or a.get("call") or {}
            if manda.get("path"):
                base = COCKPIT if sistema == "cockpit" else XRISE
                url = base.rstrip("/") + "/" + str(manda["path"]).lstrip("/")
                # El verbo por omision NO es el mismo en las dos colas: el cockpit usa PATCH y
                # Xrise POST. Suponer uno para las dos ya costo un falso negativo al recolectar.
                metodo = (manda.get("verb") or ("PATCH" if sistema == "cockpit" else "POST")).upper()
                cuerpo = manda.get("body") or {}
        fuera.append(Accion(
            etiqueta=sin_adornos(etiqueta) or etiqueta,
            op=ficha.op if ficha else None,
            efecto=efecto,
            coste_api=bool(ficha and ficha.coste_api),
            url=url,
            reversible=bool(ficha and getattr(ficha, "reversible", False)),
            metodo=metodo,
            cuerpo=cuerpo,
            # Por omision True: los avisos del feed no traen la marca y ahi Zeno ya disparaba.
            se_puede_ejecutar=bool(a.get("zeno_puede", True)),
        ))
    return fuera


def _filas(datos) -> list:
    """Las filas de un feed de avisos, se llame como se llame la clave.

    EL FALLO QUE ESTO ARREGLA, y estuvo desde el primer dia: el cockpit devuelve
    `{"unread": n, "rows": [...]}` y aqui se leia `datos.get("items", [])`, o sea CERO. Las ocho
    filas del cockpit se tiraban enteras y en la pantalla solo salia lo de Xrise.

    Y no se noto porque el RECUENTO viene de otro sitio (`/aios/pendiente-todo`) y salia bien: los
    113 pendientes de arriba eran correctos mientras la lista de abajo estaba coja. Un numero que
    cuadra al lado de una lista que no, y nadie mira que sean la misma fuente.

    Por eso se aceptan las dos claves en vez de cambiar una por otra: dos sistemas distintos las
    nombran distinto, y el dia que aparezca un tercero no puede volver a fallar en silencio.
    """
    if isinstance(datos, list):
        return datos
    if not isinstance(datos, dict):
        return []
    for clave in ("rows", "items", "notifications", "data"):
        v = datos.get(clave)
        if isinstance(v, list):
            return v
    return []


def pendientes() -> tuple[list[Pendiente], list[dict], list[str]]:
    """Lo de los dos feeds, partido en dos: lo que se DECIDE y lo que solo AVISA.

    Devuelve (para decidir, avisos sueltos, fallos). Los dos salen de la MISMA lectura: antes los
    avisos se pedian por su cuenta y eso repetia las dos llamadas en cada carga de pantalla, y del
    lado del cockpit cada una recalcula la agenda entera.

    Los avisos sin boton no se pueden decidir desde aqui, pero existen: esconderlos hacia que el
    cockpit enseñara ocho cosas y Zeno dos, que es como el operador descubrio que faltaban.
    """
    indice = _indice_del_catalogo()
    fuera, avisos, fallos = [], [], []

    datos, err = _seguro(COCKPIT, "/notifications?limit=60")
    if err:
        fallos.append(f"Zenvrax (cockpit): {err}")
    else:
        for n in _filas(datos):
            acc = _acciones("cockpit", n.get("actions"), indice)
            if not acc:
                avisos.append(_aviso_suelto("cockpit", n))
                continue
            fuera.append(Pendiente(negocio=NEGOCIO["cockpit"],
                                   titulo=sin_adornos(n.get("title")) or "?",
                                   cuerpo=(n.get("body") or "").strip(), acciones=acc,
                                   fuente="cockpit"))

    datos, err = _seguro(XRISE, "/dashboard/notifications", {"X-Zeno-Org": ORG})
    if err:
        fallos.append(f"GutLyn (Xrise): {err}")
    else:
        for n in _filas(datos):
            acc = _acciones("xrise", n.get("actions"), indice)
            if not acc:
                avisos.append(_aviso_suelto("xrise", n))
                continue
            fuera.append(Pendiente(negocio=NEGOCIO["xrise"],
                                   titulo=sin_adornos(n.get("title")) or "?",
                                   cuerpo=(n.get("body") or "").strip(), acciones=acc,
                                   fuente="xrise"))

    # Primero lo que al aprobarlo sale al mundo: es lo que no se puede deshacer.
    fuera.sort(key=lambda p: (not p.publica_algo, p.negocio, p.titulo))
    return fuera, [a for a in avisos if a["titulo"]], fallos


#: Como viene el identificador de una tarea en el feed: "task:<uuid>". Se reconoce por el prefijo
#: en vez de adivinar por el `kind`, porque el prefijo es lo que trae el dato.
_TAREA = "task:"


def _aviso_suelto(sistema: str, n: dict) -> dict:
    """Un aviso que no trae boton del sistema.

    Lleva su CUERPO: el feed ya lo manda y Zeno lo tiraba, asi que para saber de que iba una cosa
    habia que abrir el cockpit. Enseñarlo aqui quita la mitad de los saltos entre aplicaciones.

    Y si es una TAREA, lleva ademas la accion de cerrarla. Es lo unico que Zeno puede cambiar en el
    cockpit, y se arma aqui porque aqui es donde se sabe que lo es.
    """
    ident = str(n.get("id") or "")
    aviso = {
        "negocio": NEGOCIO[sistema],
        "titulo": sin_adornos(n.get("title") or n.get("label") or ""),
        "cuerpo": sin_adornos(n.get("body") or "")[:600],
        "grave": (n.get("severity") or n.get("tone")) in ("bad", "urgent", "error"),
        "url": enlaza(sistema, n.get("url") or n.get("link") or ""),
        "acciones": [],
    }
    if sistema == "cockpit" and ident.startswith(_TAREA):
        aviso["acciones"] = [{
            "etiqueta": "Marcar hecha",
            "op": "cockpit.tarea_hecha",
            # Cambia un estado y se deshace volviendo a abrirla: no sale al mundo, asi que no pide
            # PIN. El PIN es para lo que no se puede recoger.
            "efecto": "cambia_estado",
            "coste_api": False,
            "url": f"{COCKPIT.rstrip('/')}/ops/tasks/{ident[len(_TAREA):]}",
            "metodo": "PATCH",
            "cuerpo": {"status": "done"},
            "se_puede_abrir": False,
            # Se deshace volviendo a abrir la tarea, asi que se puede cerrar hablando.
            "reversible": True,
        }]
    return aviso


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


def colas_que_se_abren() -> tuple[dict, list[str]]:
    """Que colas se pueden abrir enteras, por sistema. Hoy solo las del cockpit.

    Se PREGUNTA en vez de darlo por sabido: Zeno vive fuera y una lista escrita aqui a mano se
    queda vieja en cuanto el cockpit añade o quita una cola, sin que nada falle.
    """
    fuera, fallos = {}, []
    for sistema, base, ruta, cab in (("cockpit", COCKPIT, "/aios/colas", None),
                                     ("xrise", XRISE, "/dashboard/colas", {"X-Zeno-Org": ORG})):
        datos, err = _seguro(base, ruta, cab)
        if err:
            fallos.append(f"{NEGOCIO[sistema]} (colas): {err}")
            fuera[sistema] = []
        else:
            fuera[sistema] = list(datos.get("colas") or [])
    return fuera, fallos


def elementos_de_cola(cola: str, limite: int = 25) -> tuple[list[dict], str, dict]:
    """Los ELEMENTOS de una cola del cockpit, con sus acciones ya cruzadas con el contrato.

    POR QUE EXISTE. `pendiente_completo` da el recuento, y con un numero no se decide nada: Zeno
    enseñaba "44 posts de X sin publicar" y un enlace de vuelta al cockpit, que es justo lo que el
    operador queria dejar de abrir.

    Las acciones pasan por el MISMO cruce con el catalogo que las del feed (`_acciones`): sin eso
    serian botones sin contrato, o sea texto muerto que el ejecutor rechazaria.
    """
    cuales, _ = colas_que_se_abren()
    sistema = "xrise" if cola in (cuales.get("xrise") or []) else "cockpit"
    if sistema == "xrise":
        datos, err = _seguro(XRISE, f"/dashboard/cola/{cola}?limite={int(limite)}",
                             {"X-Zeno-Org": ORG})
    else:
        datos, err = _seguro(COCKPIT, f"/aios/cola/{cola}?limite={int(limite)}")
    if err:
        return [], err, {}
    # Un fallo parcial del otro lado (que no responda la base del organico, por ejemplo) viaja
    # tal cual: una lista corta sin aviso se lee como "no hay nada pendiente".
    for f in datos.get("fallos") or []:
        err = f
    indice = _indice_del_catalogo()
    fuera = []
    for e in datos.get("elementos") or []:
        acc = _acciones(sistema, e.get("actions"), indice)
        fuera.append({
            "id": e.get("id"),
            "negocio": NEGOCIO[sistema],
            "titulo": sin_adornos(e.get("titulo")) or "?",
            "cuerpo": (e.get("cuerpo") or "").strip(),
            "cuando": e.get("cuando"),
            # Las dos piezas que cierran el circulo en las colas de trabajo diario: a donde hay
            # que ir (el post de X, el perfil de LinkedIn) y que texto llevarse. Sin el enlace
            # habria que buscar el sitio a mano, que es la mitad del esfuerzo.
            "donde": (e.get("donde") or "").strip(),
            "copiar": (e.get("copiar") or "").strip(),
            # QUE es esto: una nota de conexion, el M2 de un arco, una respuesta. Sin saberlo, el
            # texto de al lado no se puede pegar en ningun sitio con criterio.
            "paso": (e.get("etiqueta_paso") or "").strip(),
            # Si mandarlo hoy se pasaria del cupo de LinkedIn. Se enseña igual: esconderlo no
            # impide que nadie lo haga, y lo que impide decidir es no verlo.
            "fuera_de_cupo": bool(e.get("fuera_de_cupo")),
            "acciones": [{"etiqueta": a.etiqueta, "op": a.op, "efecto": a.efecto,
                          "coste_api": a.coste_api, "url": a.url,
                          "se_puede_abrir": a.se_puede_abrir, "reversible": a.reversible,
                          "metodo": a.metodo, "cuerpo": a.cuerpo,
                          "se_puede_ejecutar": a.se_puede_ejecutar}
                         for a in acc],
        })
    return fuera, "", datos.get("resumen") or {}


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

    limpia = sin_adornos

    plan = datos.get("plan") or []
    foco_bruto = datos.get("focus") or {}
    # El foco SALE de la lista de urgentes. Visto en pantalla: la tarjeta grande de "lo primero de
    # hoy" y la primera linea de "urgente" eran la misma tarea, o sea el sitio mas valioso de la
    # pantalla gastado en decir dos veces lo mismo.
    # Se compara por id, y si no hay id, por titulo. Con `p.get("id") != foco.get("id")` a secas,
    # un plan SIN ids hacia que None coincidiera con None y desaparecieran TODAS las urgentes: el
    # arreglo de un duplicado se llevaba la lista entera. Lo encontro un test.
    def es_el_foco(p):
        if foco_bruto.get("id"):
            return p.get("id") == foco_bruto["id"]
        return bool(foco_bruto.get("title")) and p.get("title") == foco_bruto.get("title")

    urgentes = [p for p in plan if p.get("severity") == "urgent" and not es_el_foco(p)]
    cuentas = datos.get("counts") or {}
    foco = datos.get("focus") or {}
    return {
        "foco": {"titulo": limpia(foco.get("title")), "tipo": foco.get("kind"),
                 "severidad": foco.get("severity"), "url": enlaza("cockpit", foco.get("url")),
                 "cuerpo": (foco.get("body") or "")[:300]} if foco.get("title") else None,
        "urgentes": [{"titulo": limpia(p.get("title")), "tipo": p.get("kind"),
                      "url": enlaza("cockpit", p.get("url"))} for p in urgentes],
        # El resto del plan viaja para que el resumen escrito lo tenga en cuenta, aunque la pantalla
        # solo enseñe lo urgente: decidir bien necesita ver todo, enseñar bien necesita ver poco.
        "resto": [{"titulo": limpia(p.get("title")), "tipo": p.get("kind"),
                   "severidad": p.get("severity"), "url": enlaza("cockpit", p.get("url"))}
                  for p in plan if p.get("severity") != "urgent" and not es_el_foco(p)],
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
                              "donde": enlaza("cockpit", a.get("to"))})
    xr, f2 = _seguro(XRISE, "/dashboard/executive", {"X-Zeno-Org": ORG})
    if f2:
        fallos.append(f"los avisos de GutLyn: {f2}")
    else:
        for a in (xr.get("alerts") or []):
            if a.get("tone") in ("warn", "bad"):
                fuera.append({"negocio": "GutLyn+",
                              "texto": f"{a.get('label')}: {a.get('value')}",
                              "grave": a.get("tone") == "bad",
                              "donde": enlaza("xrise", a.get("link"))})
    return fuera, fallos
