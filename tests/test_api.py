# -*- coding: utf-8 -*-
"""El servicio de Zeno no ejecuta nada, y no disimula lo que no pudo leer.

EL CASO. Zeno es la pieza que el operador va a tener en el móvil, y en J4 ejecutará acciones que
publican en su nombre. Hasta entonces la promesa de la fase es que **solo lee**. Una promesa así se
rompe en una línea y ninguna prueba manual la detecta: un POST contra una API que responde 200 se ve
igual de bien en la pantalla.

Y hay un fallo que sería peor que un error visible: que el servicio se coma la caída de un sistema.
Si el cockpit no contesta y Zeno devuelve la lista de GutLyn sin decir nada, el operador lee "hay una
cosa pendiente" cuando la verdad es "hay una que he podido ver". Con eso se toman decisiones.

Puros: sin red. Se sustituyen el lector y la sesión.
"""
import ast
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fastapi = pytest.importorskip("fastapi", reason="el servicio necesita fastapi")
from fastapi.testclient import TestClient            # noqa: E402

import lector                                        # noqa: E402
from servicio import api as api_mod, sesion          # noqa: E402

cliente = TestClient(api_mod.app)
CABECERA = {"Authorization": "Bearer jwt-bueno"}


@pytest.fixture(autouse=True)
def _sesion_valida(monkeypatch):
    monkeypatch.setattr(sesion, "quien_es",
                        lambda t, ahora=None: sesion.Quien("u1", "owner", "yo@zenvrax.com"))
    # El recuento por cola sale a la red en produccion: aqui se silencia salvo que el test lo pise.
    monkeypatch.setattr(lector, "pendiente_completo", lambda: ([], []))
    yield
    sesion.limpiar_cache()


# ---------------------------------------------------------------- no ejecuta

def test_el_servicio_no_hace_ninguna_llamada_que_no_sea_get_hacia_los_dos_sistemas():
    """Del árbol del lector, que es quien habla con el cockpit y con Xrise. El servicio es una
    fachada: si alguien mete aquí un POST hacia fuera, deja de ser la fase que no rompe nada."""
    arbol = ast.parse((RAIZ / "lector.py").read_text(encoding="utf-8"))
    metodos = [kw.value.value for n in ast.walk(arbol) if isinstance(n, ast.Call)
               for kw in n.keywords if kw.arg == "method" and isinstance(kw.value, ast.Constant)]
    assert metodos and set(metodos) == {"GET"}, f"el lector hace peticiones que no son GET: {set(metodos)}"


def test_no_hay_ningun_endpoint_que_ejecute_una_accion():
    """Los únicos POST del servicio son entrar, salir y el chat (apagado). Un POST que dispare una
    acción del catálogo sería J4 entrando por la puerta de atrás."""
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))
    posts = []
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for d in n.decorator_list:
            f = d.func if isinstance(d, ast.Call) else d
            if isinstance(f, ast.Attribute) and f.attr in ("post", "put", "patch", "delete"):
                posts.append(n.name)
    assert sorted(posts) == ["chat", "login", "login_2fa", "salir"], (
        f"endpoints que escriben y no deberían existir todavía: {sorted(posts)}")


def test_el_chat_nace_apagado_porque_gasta_dinero():
    """Medido: ~$0,006 por pregunta. Encenderlo por defecto sería gastar sin haberlo puesto delante
    del operador, que es justo lo que su regla prohíbe."""
    r = cliente.post("/api/chat", headers=CABECERA, json={"texto": "hola"})
    assert r.status_code == 501
    assert "tu OK" in r.json()["detail"], "el mensaje tiene que decir POR QUÉ está apagado"
    assert api_mod.CHAT_ACTIVO is False, "de serie, apagado"


# ---------------------------------------------------------------- no disimula

def test_los_fallos_viajan_siempre_aunque_esten_vacios(monkeypatch):
    """Si `fallos` solo apareciera cuando hay alguno, el front tendría que adivinar si una lista
    corta es "hay poco" o "no he podido leer la mitad"."""
    monkeypatch.setattr(lector, "pendientes", lambda: ([], []))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()
    assert "fallos" in d and d["fallos"] == []


def test_un_sistema_caido_sale_en_la_respuesta(monkeypatch):
    monkeypatch.setattr(lector, "pendientes",
                        lambda: ([], ["Zenvrax (cockpit): HTTP 502 en /notifications"]))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()
    assert d["fallos"], "la caída no puede desaparecer entre la lectura y la respuesta"


def test_cada_pendiente_lleva_si_publica_y_si_cuesta(monkeypatch):
    """Es lo que Zeno aporta sobre mirar las dos pantallas. Sin estos campos, el front no puede
    marcar lo irreversible ni lo que gasta."""
    p = lector.Pendiente(negocio="GutLyn", titulo="Post", cuerpo="", acciones=[
        lector.Accion("Aprobar y publicar", "claire.aprobar_y_publicar", "publica", False),
        lector.Accion("Regenerar", "claire.regenerar", "cambia_estado", True)])
    monkeypatch.setattr(lector, "pendientes", lambda: ([p], []))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()["pendientes"][0]
    assert d["publica_algo"] is True and d["cuesta_dinero"] is True
    assert d["acciones"][0]["efecto"] == "publica"


def test_la_busqueda_dice_en_que_modo_respondio(monkeypatch):
    """Contestar "no hay nada" con el servicio de significado caído es mentir con cara de certeza."""
    monkeypatch.setattr(lector, "documentacion", lambda q: ([], "texto", []))
    d = cliente.get("/api/buscar?q=precios", headers=CABECERA).json()
    assert d["modo"] == "texto"


# ---------------------------------------------------------------- caído no es lo mismo que fuera

def test_el_cockpit_caido_devuelve_503_y_no_401(monkeypatch):
    """EL TEST QUE IMPORTA. Con 401 el front borra el token y echa al operador al login cada vez que
    el cockpit se reinicia. Es el incidente de agosto de 2026 en el propio cockpit."""
    def cae(t, ahora=None):
        raise sesion.CockpitNoResponde("timeout")
    monkeypatch.setattr(sesion, "quien_es", cae)
    assert cliente.get("/api/pendientes", headers=CABECERA).status_code == 503


def test_una_sesion_invalida_si_devuelve_401(monkeypatch):
    def fuera(t, ahora=None):
        raise sesion.NoAutenticado("token malo")
    monkeypatch.setattr(sesion, "quien_es", fuera)
    assert cliente.get("/api/pendientes", headers=CABECERA).status_code == 401


def test_sin_cabecera_no_se_entra(monkeypatch):
    def fuera(t, ahora=None):
        raise sesion.NoAutenticado("sin token")
    monkeypatch.setattr(sesion, "quien_es", fuera)
    for ruta in ("/api/pendientes", "/api/buscar?q=hola", "/api/yo"):
        assert cliente.get(ruta).status_code == 401, f"{ruta} deja pasar sin sesión"


def test_la_salud_no_pide_sesion():
    """La mira el despliegue para saber si el contenedor vive: pedirle sesión lo dejaría siempre en
    rojo y el arranque no se daría nunca por bueno."""
    r = cliente.get("/api/salud")
    assert r.status_code == 200 and r.json()["ok"] is True


# ---------------------------------------------------------------- el chat, con Haiku y con tope

def test_el_chat_usa_haiku_y_no_sonnet():
    """El operador: *"el modelo debería ser haiku"*. Medido sobre 30 días reales del ecosistema,
    Haiku sale a $0,0017 por llamada y Sonnet a $0,0079: 4,5 veces más caro para contestar sobre un
    contexto que Zeno ya tiene delante. La voz la pone el prompt, no el modelo."""
    from servicio import chat as chat_mod
    assert "haiku" in chat_mod.MODELO.lower(), (
        f"el chat usa {chat_mod.MODELO}: encarece cada pregunta sin mejorar la respuesta")


def test_el_chat_tiene_tope_diario():
    """Es la única pieza de Zeno cuyo coste lo decide el uso y no el sistema. Sin tope, una tarde de
    curiosidad se convierte en una factura que nadie vio venir."""
    from servicio import chat as chat_mod
    assert 0 < chat_mod.TOPE_DIARIO <= 200, f"tope raro: {chat_mod.TOPE_DIARIO}"


def test_cada_respuesta_dice_lo_que_ha_costado(monkeypatch):
    """Sin la cifra en pantalla, el gasto solo se ve en la factura de fin de mes."""
    from servicio import chat as chat_mod
    import inspect
    fuente = inspect.getsource(chat_mod.responde)
    for campo in ("coste_usd", "preguntas_hoy", "tope_diario", "modelo"):
        assert campo in fuente, f"la respuesta del chat no dice {campo}"


def test_el_chat_no_promete_ejecutar():
    """Zeno todavía no ejecuta: eso es J4. Si el prompt no se lo prohíbe, el modelo dirá que sí
    puede, y el operador se quedará esperando algo que no va a pasar."""
    from servicio import chat as chat_mod
    assert "no puedes" in chat_mod.SISTEMA or "todavía no puedes" in chat_mod.SISTEMA
    assert "Inventar" in chat_mod.SISTEMA, "el prompt tiene que prohibir inventar cifras"
