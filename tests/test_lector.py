# -*- coding: utf-8 -*-
"""Zeno leyendo: no escribe nunca, y no disimula lo que no ha podido leer.

La fase J2 dice que Zeno SOLO lee, y eso es lo que la hace segura: no puede romper nada. Pero "solo
lee" es una promesa que se rompe en una linea, y ninguna prueba manual la detecta, porque un POST
contra una API que responde 200 se ve igual de bien en la pantalla.

El otro riesgo es mas sutil y es el que de verdad haria dañino a Zeno: que se coma un fallo. Si el
cockpit no contesta y Zeno imprime la lista de GutLyn sin decir nada, el operador lee "hay una cosa
pendiente" cuando la verdad es "hay una que he podido ver". Con eso se toman decisiones.

Puros: sin red. Las respuestas de las dos APIs se sustituyen por datos de mentira.
"""
import ast
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import lector                                    # noqa: E402
import catalogo as C                             # noqa: E402


# --------------------------------------------------------------- no escribe

def test_el_lector_no_hace_ninguna_peticion_que_no_sea_get():
    """Del ARBOL, no del texto: cualquier `method=` distinto de GET en el lector es una escritura."""
    arbol = ast.parse((RAIZ / "lector.py").read_text(encoding="utf-8"))
    metodos = [kw.value.value for nodo in ast.walk(arbol) if isinstance(nodo, ast.Call)
               for kw in nodo.keywords
               if kw.arg == "method" and isinstance(kw.value, ast.Constant)]
    assert metodos, "no se ha encontrado ninguna peticion: el test dejó de mirar donde debía"
    assert set(metodos) == {"GET"}, f"el lector hace peticiones que no son GET: {set(metodos)}"


def test_la_orden_de_consola_no_ejecuta_acciones():
    """`zeno.py` imprime lo pendiente y sus botones. Si llamara a una de esas acciones, dejaría de ser
    la fase que no puede romper nada."""
    src = (RAIZ / "zeno.py").read_text(encoding="utf-8")
    for prohibido in ("urllib.request.urlopen", "requests.post", "method=\"POST\""):
        assert prohibido not in src, f"zeno.py no puede hacer peticiones por su cuenta: {prohibido}"


# --------------------------------------------------------------- no disimula

def _finge(respuestas: dict, fallan=()):
    """Sustituye `_pide` por respuestas de mentira. `fallan` son las rutas que revientan."""
    def falso(base, ruta, cabeceras=None):
        for trozo in fallan:
            if trozo in ruta:
                raise RuntimeError("caido")
        for trozo, datos in respuestas.items():
            if trozo in ruta:
                return datos
        return []
    return falso


AVISO_XRISE = {"title": "Post de Claire", "body": "cuerpo",
               "actions": [{"label": "✅ Aprobar y publicar"}, {"label": "🔄 Regenerar"}]}
AVISO_COCKPIT = {"title": "Tema del pool", "body": "cuerpo",
                 "actions": [{"label": "✅ Marcar publicado"}]}


def test_si_un_sistema_no_contesta_se_dice_y_no_se_calla(monkeypatch):
    """EL TEST QUE IMPORTA. Una lista corta sin aviso se lee como "hay poco pendiente"."""
    monkeypatch.setattr(lector, "CLAVE", "x")
    monkeypatch.setattr(lector, "_pide", _finge({"/dashboard/notifications": [AVISO_XRISE]},
                                               fallan=("/notifications?limit",)))
    lista, fallos = lector.pendientes()
    assert len(lista) == 1, "lo que sí se pudo leer tiene que salir"
    assert any("cockpit" in f for f in fallos), (
        "el sistema que no contestó tiene que aparecer en los fallos, no desaparecer")


def test_una_accion_que_el_catalogo_no_reconoce_se_marca_y_no_se_oculta(monkeypatch):
    """Si Zeno esconde lo que no entiende, el operador ve una lista incompleta sin saberlo."""
    monkeypatch.setattr(lector, "CLAVE", "x")
    inventada = {"title": "Algo nuevo", "body": "", "actions": [{"label": "🆕 Boton recien puesto"}]}
    monkeypatch.setattr(lector, "_pide", _finge({"/dashboard/notifications": [inventada]},
                                               fallan=("/notifications?limit",)))
    lista, _ = lector.pendientes()
    assert len(lista) == 1
    assert lista[0].sin_contrato == 1, "una acción sin contrato tiene que contarse"
    assert lista[0].acciones[0].op is None


# --------------------------------------------------------------- lo peligroso va primero

def test_lo_que_sale_al_mundo_se_ordena_primero(monkeypatch):
    """El operador lee de arriba abajo. Lo irreversible no puede quedar debajo de una anotación.

    Los datos están elegidos para que el orden ALFABÉTICO dé lo contrario del correcto: el que
    publica es de Zenvrax y el que no, de GutLyn. La primera versión de este test usaba lo contrario
    y pasaba igual con el orden roto, porque "GutLyn" va antes que "Zenvrax" y acertaba por
    casualidad. Se vio quitando el orden a propósito, no leyendo el test.
    """
    monkeypatch.setattr(lector, "CLAVE", "x")
    publica_cockpit = {"title": "Post de LinkedIn", "body": "",
                       "actions": [{"label": "✅ Aprobar"}]}          # PUBLICA en LinkedIn
    no_publica_xrise = {"title": "Respuesta propuesta", "body": "",
                        "actions": [{"label": "🗑️ Descartar respuesta"}]}   # solo cambia estado
    monkeypatch.setattr(lector, "_pide", _finge({
        "/notifications?limit": [publica_cockpit],
        "/dashboard/notifications": [no_publica_xrise],
    }))
    lista, fallos = lector.pendientes()
    assert not fallos
    assert len(lista) == 2
    assert lista[0].publica_algo, "lo que publica va primero, aunque su negocio sea el último"
    assert lista[0].negocio == "Zenvrax"
    assert not lista[1].publica_algo


def test_marca_lo_que_cuesta_dinero(monkeypatch):
    """Hay una regla dura sobre no gastar sin permiso. Zeno no puede respetarla si no sabe cuál gasta."""
    monkeypatch.setattr(lector, "CLAVE", "x")
    monkeypatch.setattr(lector, "_pide", _finge({"/dashboard/notifications": [AVISO_XRISE]},
                                               fallan=("/notifications?limit",)))
    lista, _ = lector.pendientes()
    assert lista[0].cuesta_dinero, "Regenerar gasta una llamada de pago y hay que decirlo"


def test_las_etiquetas_del_aviso_cuadran_con_el_catalogo():
    """El cruce se hace por (sistema, etiqueta). Si una cola cambia el texto de un botón sin tocar el
    catálogo, Zeno deja de saber qué hace esa acción: aquí se comprueba que hoy cuadran."""
    indice = lector._indice_del_catalogo()
    assert ("xrise", "✅ Aprobar y publicar") in indice
    assert ("cockpit", "✅ Marcar publicado") in indice
    ficha = indice[("xrise", "✅ Aprobar y publicar")]
    assert ficha.efecto == C.PUBLICA


# ---------------------------------------------------------------- los dos negocios a la par

def _pon(monkeypatch, est=None, ventas=None, colas=None, fallos=()):
    monkeypatch.setattr(lector, "estado", lambda: (est or {}, list(fallos)))
    monkeypatch.setattr(lector, "ventas_gutlyn", lambda: (ventas or {}, []))
    monkeypatch.setattr(lector, "pendiente_completo", lambda: (colas or [], []))


def test_los_dos_negocios_salen_aunque_uno_no_conteste(monkeypatch):
    """EL TEST QUE IMPORTA de esta pantalla. Si Xrise esta caido y GutLyn desaparece de la vista, el
    operador ve una sola tarjeta y lee "solo tengo un negocio", no "no he podido leer el otro"."""
    _pon(monkeypatch, est={}, ventas={}, fallos=["ventas de GutLyn (resumen): HTTP 502"])
    lista, sueltos = lector.negocios()
    assert [b["id"] for b in lista] == ["zenvrax", "gutlyn"]
    assert any("502" in f for f in lista[1]["fallos"]), (
        "el fallo tiene que ir DENTRO de la tarjeta de GutLyn, no en un monton comun")
    assert sueltos == []


def test_un_cero_es_un_cero_y_no_se_disfraza_de_falta_de_dato(monkeypatch):
    """Ya paso con el chat: leyo los ceros de GutLyn y contesto que no tenia el dato. Cero ventas es
    una respuesta, y ademas es la verdad hasta que arranque la tienda."""
    _pon(monkeypatch, ventas={"resumen": {"revenue": 0.0, "orders": 0, "net_profit": 0.0}})
    g = [b for b in lector.negocios()[0] if b["id"] == "gutlyn"][0]
    por = {k["k"]: k["v"] for k in g["kpis"]}
    assert por["Ingresos 30d"] == "$0"
    assert por["Pedidos"] == "0"
    # Y lo que de verdad falta si se dice que falta, sin inventar un cero.
    assert por["Margen"] == "sin dato"


def test_lo_pendiente_se_reparte_por_negocio(monkeypatch):
    """Sumar 113 en un solo numero no dice a cual de los dos hay que atender hoy."""
    _pon(monkeypatch, colas=[
        {"negocio": "Zenvrax", "titulo": "Posts de X", "cuantos": 44, "donde": "/x"},
        {"negocio": "GutLyn", "titulo": "Posts por aprobar", "cuantos": 17, "donde": "/g"},
        {"negocio": "gutlyn", "titulo": "Correos", "cuantos": 3, "donde": "/c"}])
    porid = {b["id"]: b for b in lector.negocios()[0]}
    assert porid["zenvrax"]["pendiente"] == 44
    # Dos colas del mismo negocio escritas distinto son el MISMO negocio: si no, GutLyn saldria a la
    # mitad de lo que tiene y nadie lo notaria.
    assert porid["gutlyn"]["pendiente"] == 20
    assert len(porid["gutlyn"]["colas"]) == 2


def test_el_beneficio_negativo_se_marca(monkeypatch):
    """Es el unico numero de la tarjeta que cambia una decision al verlo. Sin marca, un menos se
    lee igual que un mas en una rejilla de ocho cifras."""
    _pon(monkeypatch, ventas={"resumen": {"net_profit": -320.0}})
    g = [b for b in lector.negocios()[0] if b["id"] == "gutlyn"][0]
    ben = [k for k in g["kpis"] if k["k"] == "Beneficio neto"][0]
    assert ben["alerta"] == "bad" and ben["v"].startswith("$-")


def test_los_kpi_de_zenvrax_se_pasan_tal_cual(monkeypatch):
    """El cockpit ya los calcula con su alerta y su enlace. Recalcularlos aqui seria el mismo dato
    en dos sitios, que en esta casa ya ha causado tres incidentes."""
    _pon(monkeypatch, est={"zenvrax": {"negocios": [
        {"id": "zenvrax", "nombre": "Zenvrax IO",
         "kpis": [{"k": "Runway", "v": "11 meses", "alerta": "warn", "to": "/finanzas/pnl"}]},
        {"id": "gutlyn", "nombre": "GutLyn+", "kpis": []}]}})
    z = [b for b in lector.negocios()[0] if b["id"] == "zenvrax"][0]
    assert z["kpis"] == [{"k": "Runway", "v": "11 meses", "alerta": "warn", "to": "/finanzas/pnl"}]


def test_el_hecho_hoy_del_cockpit_no_se_enseña_como_trabajo(monkeypatch):
    """MEDIDO EL 2026-09-27: `done_today` trae 13 entradas y son accesos a la aplicacion (logins,
    segundos factores), no trabajo terminado. Enseñarlo como "lo hecho hoy" diria 13 cosas hechas
    cuando no se ha hecho ninguna, que es peor que no decir nada."""
    monkeypatch.setattr(lector, "_seguro", lambda b, r, c=None: ({
        "focus": {"title": "Una cosa"}, "plan": [], "counts": {},
        "done_today": [{"action": "login_2fa_success"}] * 13}, None))
    plan, _ = lector.plan_del_dia()
    assert "done_today" not in plan and "hecho" not in json.dumps(plan)


def test_solo_salen_los_avisos_que_no_estan_bien(monkeypatch):
    """Ocho semaforos en verde no son informacion, son ruido que entrena a no mirar. De los ocho de
    Xrise medidos hoy, solo uno esta en ambar."""
    def falso(base, ruta, cab=None):
        if "overview" in ruta:
            return {"agenda": [{"negocio": "Zenvrax IO", "texto": "Runway: 11 meses", "sev": "warn"},
                               {"negocio": "Zenvrax IO", "texto": "Todo bien", "sev": "ok"}]}, None
        return {"alerts": [{"label": "Signups sin contactar", "value": 57, "tone": "warn"},
                           {"label": "SKUs en rotura", "value": 0, "tone": "ok"},
                           {"label": "Pedidos abiertos", "value": 0, "tone": "ok"}]}, None
    monkeypatch.setattr(lector, "_seguro", falso)
    avisos, _ = lector.alertas()
    assert len(avisos) == 2, [a["texto"] for a in avisos]
    assert any("57" in a["texto"] for a in avisos)
    assert not any("rotura" in a["texto"] for a in avisos)


def test_el_titulo_pierde_el_emoji_y_la_raya_larga(monkeypatch):
    """Los titulos del cockpit vienen con un emoji delante y raya larga en medio. El emoji es
    decoracion de otra pantalla y roba sitio en un movil; la raya larga esta prohibida en todo lo
    que sale de esta casa, y colarse por un dato leido cuenta igual.

    EL ORDEN IMPORTA y lo aprendi probandolo: si se filtra antes de sustituir, el filtro se come la
    raya y deja dos espacios en medio de la frase.
    """
    monkeypatch.setattr(lector, "_seguro", lambda b, r, c=None: (
        {"focus": {"title": "\U0001f5c2\ufe0f Tarea \u2014 La versión inglesa no existe"},
         "plan": [{"title": "\U0001f4ac Respuesta a DM \u2014 Era Emre", "severity": "urgent"}],
         "counts": {}}, None))
    plan, _ = lector.plan_del_dia()
    assert plan["foco"]["titulo"] == "Tarea, La versión inglesa no existe"
    assert plan["urgentes"][0]["titulo"] == "Respuesta a DM, Era Emre"
    for t in (plan["foco"]["titulo"], plan["urgentes"][0]["titulo"]):
        assert "\u2014" not in t and "  " not in t
        assert t == t.strip()
