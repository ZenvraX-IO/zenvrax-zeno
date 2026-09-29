# -*- coding: utf-8 -*-
"""Quitar un correo de Zeno sin tocar Gmail.

EL CASO (2026-09-29). El operador preguntó si se podía borrar correo desde Zeno. Medido contra la
documentación de Google: el permiso concedido (`gmail.readonly` + `gmail.compose`) no deja ni mover
a la papelera ni archivar; haría falta autorizar `gmail.modify`. Al ponerle las opciones delante,
aclaró lo que de verdad quería:

    *"Lo único es no verlo en Zeno, aun cuando siga en Gmail."*

Y eso no necesita ningún permiso nuevo. Es una lista en el volumen de Zeno.

LA DIFERENCIA IMPORTA Y ESTE FICHERO LA DEFIENDE: si mañana alguien "mejora" esto llamando a Gmail
para archivar de verdad, el peor caso deja de ser "vuelven a verse unos correos" y pasa a ser
"desapareció correo del buzón". No es la misma pieza.
"""
import importlib
import json
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fastapi = pytest.importorskip("fastapi", reason="el servicio necesita fastapi")
from fastapi.testclient import TestClient            # noqa: E402

from servicio import api as api_mod, sesion          # noqa: E402

cliente = TestClient(api_mod.app)
CABECERA = {"Authorization": "Bearer jwt-bueno"}


@pytest.fixture(autouse=True)
def _sesion(monkeypatch):
    monkeypatch.setattr(sesion, "quien_es",
                        lambda t, ahora=None: sesion.Quien("u1", "owner", "yo@zenvrax.com"))
    yield
    sesion.limpiar_cache()


@pytest.fixture()
def oc(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENO_OCULTOS", str(tmp_path / "oculto.json"))
    from servicio import ocultos
    o = importlib.reload(ocultos)
    monkeypatch.setattr(api_mod, "ocultos", o)
    return o


# ---------------------------------------------------------------- no toca Gmail

def test_ocultar_no_llama_a_gmail():
    """LA BARRERA. Esto existe PORQUE no hace falta permiso para escribir en Gmail. Si un día
    llamara a la API para archivar o tirar a la papelera, haría falta `gmail.modify` y el peor
    caso de un error pasaría de "vuelven a verse unos correos" a "desapareció correo del buzón"."""
    import ast
    # LOS IMPORTS, no el texto. La primera version buscaba "gmail" en el fichero y saltaba por el
    # comentario que explica precisamente que NO se llama a Gmail. Lo que decide si este modulo
    # puede tocar el buzon es lo que importa, no lo que cuenta.
    arbol = ast.parse((RAIZ / "servicio" / "ocultos.py").read_text(encoding="utf-8"))
    trae = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            trae |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            trae.add((n.module or "").split(".")[0])
    prohibidos = {"google", "urllib", "requests", "httpx", "http"}
    assert not (trae & prohibidos), (
        f"el módulo de ocultos importa {sorted(trae & prohibidos)}: solo puede ser una lista local")
    assert trae <= {"json", "os", "time", "pathlib", "__future__"}, sorted(trae)


def test_el_correo_desaparece_de_la_bandeja_pero_no_del_buzon(oc, monkeypatch):
    monkeypatch.setattr(api_mod.personal, "bandeja", lambda: (
        {"correos": [{"id": "m1", "asunto": "uno"}, {"id": "m2", "asunto": "dos"}],
         "agenda": [], "cuentas": {}, "buzones": []}, []))
    assert len(cliente.get("/api/personal", headers=CABECERA).json()["correos"]) == 2
    cliente.post("/api/correo/ocultar", json={"id": "m1"}, headers=CABECERA)
    r = cliente.get("/api/personal", headers=CABECERA).json()
    assert [c["id"] for c in r["correos"]] == ["m2"]
    # `bandeja()` sigue devolviendo los dos: el correo está donde estaba.
    assert len(api_mod.personal.bandeja()[0]["correos"]) == 2


# ---------------------------------------------------------------- el deshacer

def test_se_puede_devolver_lo_quitado(oc, monkeypatch):
    """Sin deshacer, un toque por error esconde un correo para siempre y el único camino de vuelta
    es abrir Gmail, que es de lo que veníamos huyendo."""
    monkeypatch.setattr(api_mod.personal, "bandeja", lambda: (
        {"correos": [{"id": "m1"}, {"id": "m2"}], "agenda": [], "cuentas": {}, "buzones": []}, []))
    cliente.post("/api/correo/ocultar", json={"id": "m1"}, headers=CABECERA)
    cliente.post("/api/correo/ocultar", json={"id": "m2"}, headers=CABECERA)
    assert cliente.get("/api/personal", headers=CABECERA).json()["correos"] == []
    assert cliente.post("/api/correo/mostrar", headers=CABECERA).json()["vuelven"] == 2
    assert len(cliente.get("/api/personal", headers=CABECERA).json()["correos"]) == 2


def test_la_pantalla_dice_cuantos_hay_escondidos(oc, monkeypatch):
    """El contador cuenta los que se están escondiendo AHORA, no los de la lista entera: si
    contara los de hace semanas, el número no cuadraría con lo que se puede recuperar."""
    monkeypatch.setattr(api_mod.personal, "bandeja", lambda: (
        {"correos": [{"id": "m1"}], "agenda": [], "cuentas": {}, "buzones": []}, []))
    oc.oculta("m1")
    oc.oculta("viejo-que-ya-no-sale")
    assert cliente.get("/api/personal", headers=CABECERA).json()["ocultos"] == 1


# ---------------------------------------------------------------- la lista, por dentro

def test_lo_viejo_se_tira_solo(oc):
    """La bandeja solo mira siete días: a los treinta, ese correo no podría salir ni queriendo.
    Guardarlo más es una lista que crece sin que nadie la lea."""
    Path(oc.FICHERO).write_text(json.dumps({"antiguo": time.time() - 60 * 86400}),
                                encoding="utf-8")
    oc.oculta("nuevo")
    assert oc.cuales() == {"nuevo"}


def test_un_fichero_roto_no_deja_la_bandeja_en_blanco(oc, monkeypatch):
    """Si leer la lista fallara y eso tumbara `/api/personal`, un JSON a medias dejaría al
    operador sin correo en la pantalla. Vale más enseñarlo todo que no enseñar nada."""
    Path(oc.FICHERO).write_text("{roto", encoding="utf-8")
    assert oc.cuales() == set()
    monkeypatch.setattr(api_mod.personal, "bandeja", lambda: (
        {"correos": [{"id": "m1"}], "agenda": [], "cuentas": {}, "buzones": []}, []))
    assert len(cliente.get("/api/personal", headers=CABECERA).json()["correos"]) == 1


def test_sin_sesion_no_se_esconde_nada(monkeypatch):
    def _no(t, ahora=None):
        raise sesion.NoAutenticado("no")

    monkeypatch.setattr(sesion, "quien_es", _no)
    assert cliente.post("/api/correo/ocultar", json={"id": "m1"}).status_code == 401
    assert cliente.post("/api/correo/mostrar").status_code == 401


def test_un_id_vacio_no_se_guarda(oc):
    assert cliente.post("/api/correo/ocultar", json={"id": "  "},
                        headers=CABECERA).status_code == 422
    assert oc.cuantos() == 0


# ---------------------------------------------------------------- la pantalla

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def test_se_quita_deslizando_la_tarjeta():
    """Era un botón de texto y el operador lo prefirió así (29-sep): el gesto que ya se tiene en
    el dedo de usar Mail, y una tarjeta menos cargada."""
    assert "data-desliza" in WEB and '"/api/correo/ocultar"' in WEB
    assert "enchufaDeslizar" in WEB


def test_el_gesto_no_rompe_el_scroll_de_la_lista():
    """LO QUE MÁS SE ROMPE AL HACER ESTO. Sin decidir primero si el gesto es horizontal, bajar por
    la lista arrastra tarjetas de medio lado; y sin `touch-action:pan-y`, el navegador no sabe que
    el movimiento vertical sigue siendo suyo."""
    assert "touch-action:pan-y" in WEB, "falta ceder el scroll vertical al navegador"
    i = WEB.index("function enchufaDeslizar")
    cuerpo = WEB[i:i + 3000]
    assert 'Math.abs(ax) > Math.abs(ay)' in cuerpo, "el gesto se toma sin saber si es horizontal"


def test_arrastrar_no_abre_el_correo():
    """Toda la tarjeta es un enlace a Gmail: sin tragarse el clic posterior al arrastre, cada
    gesto acabaría abriendo el correo que se quería quitar."""
    i = WEB.index("function enchufaDeslizar")
    cuerpo = WEB[i:i + 3000]
    assert "preventDefault()" in cuerpo and "Math.abs(dx) >" in cuerpo


def test_solo_se_desliza_hacia_la_izquierda():
    """Hacia la derecha no hay nada que hacer, y dejarla moverse enseña un hueco vacío que parece
    un fallo."""
    i = WEB.index("function enchufaDeslizar")
    assert "Math.min(0, ax)" in WEB[i:i + 3000]


def test_si_falla_el_servidor_la_tarjeta_vuelve():
    """Dejarla fuera mintiendo es peor: al recargar reaparece y uno cree que el gesto no se
    guarda."""
    i = WEB.index("function enchufaDeslizar")
    cuerpo = WEB[i:i + 3000]
    j = cuerpo.index("} catch")
    assert "mueve(0)" in cuerpo[j:j + 300], "tras un fallo la tarjeta se queda fuera"


def test_el_correo_desaparece_al_instante():
    """Volver a pedir la bandeja tarda (habla con Gmail), y el correo se iría segundos después del
    gesto: se lee como que no ha hecho nada."""
    i = WEB.index("function enchufaDeslizar")
    cuerpo = WEB[i:i + 3000]
    assert "correosEnPantalla = correosEnPantalla.filter" in cuerpo
    assert "cargaPersonal()" not in cuerpo, "recarga la bandeja entera en vez de quitarlo y ya"


def test_el_deshacer_se_ve_en_la_pantalla():
    """Si el camino de vuelta no está a la vista, no existe."""
    assert "ver-ocultos" in WEB and '"/api/correo/mostrar"' in WEB
    i = WEB.index("ver-ocultos")
    assert "devolver" in WEB[i - 400:i + 400]
