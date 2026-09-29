# -*- coding: utf-8 -*-
"""Lo hecho: solo lo de hoy, resumido en una línea, y se borra solo.

EL CASO (2026-09-29). El operador mandó una captura de la pestaña Trabajo: veintitantas tarjetas de
"Saltar hoy" y "Respondí" de días anteriores, y el trabajo de verdad por debajo del pliegue.

    *"El histórico realizado en trabajo no debería sobrevivir más de un día, si no puede ser una
    lista interminable. Ponlo de otra manera que se vea, pero que se autoborre cada día."*

Tres cosas que protege este fichero: que el diario se limpie solo, que la pantalla enseñe solo lo
de hoy, y que vuelva a ser un resumen y no una lista.
"""
import importlib
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def dia(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENO_DIARIO", str(tmp_path / "hecho.jsonl"))
    from servicio import diario
    return importlib.reload(diario)


def _mete(d, cuando: float, **campos):
    """Escribe un renglón con la fecha que se le diga, sin pasar por `apunta`."""
    with d.LIBRO.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"cuando": cuando, **campos}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- se borra solo

def test_lo_de_hace_una_semana_se_tira_al_escribir(dia):
    """LA BARRERA. Sin esto el fichero crece para siempre y la pantalla se llena de días viejos,
    que es justo la captura que mandó el operador."""
    _mete(dia, time.time() - 7 * 86400, op="vieja", titulo="de hace una semana")
    _mete(dia, time.time() - 3 * 86400, op="vieja2", titulo="de hace tres días")
    dia.apunta({"op": "nueva", "titulo": "de ahora", "resultado": "hecho"})
    quedan = [x.get("titulo") for x in dia.lee(50)]
    assert quedan == ["de ahora"], quedan


def test_lo_de_ayer_sobrevive(dia):
    """DOS DÍAS Y NO UNO, por la frontera de medianoche: a las 00:05 lo de "hace un rato" ya es de
    ayer, y tirarlo dejaría la pantalla en blanco justo después de haber estado trabajando."""
    _mete(dia, time.time() - 3600 * 20, op="ayer", titulo="anoche")
    dia.apunta({"op": "nueva", "titulo": "de ahora"})
    assert "anoche" in [x.get("titulo") for x in dia.lee(50)]


def test_pero_en_pantalla_solo_sale_lo_de_hoy(dia):
    """Se guarda dos días y se ENSEÑA uno. Son dos cosas distintas a propósito."""
    ayer = datetime.now() - timedelta(days=1)
    _mete(dia, ayer.timestamp(), op="ayer", titulo="lo de ayer")
    dia.apunta({"op": "hoy", "titulo": "lo de hoy"})
    assert [x["titulo"] for x in dia.de_hoy()] == ["lo de hoy"]


def test_una_linea_rota_no_se_lleva_el_dia(dia):
    """Un reinicio a media escritura deja una línea partida. Si eso vaciara el fichero, se
    perdería el rastro de lo que salió al mundo, que es para lo que existe el diario."""
    dia.apunta({"op": "buena", "titulo": "antes"})
    with dia.LIBRO.open("a", encoding="utf-8") as f:
        f.write('{"cuando": 99')
    dia.apunta({"op": "buena2", "titulo": "después"})
    titulos = [x.get("titulo") for x in dia.lee(50)]
    assert "antes" in titulos and "después" in titulos


def test_el_diario_no_revienta_si_no_puede_limpiar(dia, monkeypatch):
    """Que la limpieza falle no puede tumbar una acción ya hecha: el operador vería un error
    después de haber publicado de verdad."""
    monkeypatch.setattr(dia, "LIBRO", Path("/no/existe/ni/se/puede/h.jsonl"))
    dia.apunta({"op": "x", "titulo": "y"})          # no lanza


# ---------------------------------------------------------------- la pantalla

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def test_la_pantalla_pide_el_resumen_y_no_una_lista():
    """El recuento lo hace el servidor. Si el front volviera a pedir `?cuantos=N` estaría
    trayéndose la lista entera para contarla él, que es de donde venimos."""
    i = WEB.index("async function pintaHecho")
    cuerpo = WEB[i:i + 2600]
    assert '"/api/hecho"' in cuerpo, "vuelve a pedir la lista con parámetros"
    assert "d.cuantas" in cuerpo and "d.resumen" in cuerpo


def test_el_detalle_nace_cerrado():
    """LO QUE PEDÍA EL OPERADOR. Si el detalle saliera abierto, volveríamos a las veintitantas
    tarjetas y el trabajo de verdad seguiría por debajo del pliegue."""
    i = WEB.index("async function pintaHecho")
    cuerpo = WEB[i:i + 2600]
    assert 'id="hecho-detalle" hidden' in cuerpo, "el detalle sale desplegado"


def test_un_dia_sin_nada_no_ocupa_sitio():
    """Un encabezado "Hoy has hecho" sobre una lista vacía es ruido en la pantalla que más se
    mira."""
    i = WEB.index("async function pintaHecho")
    cuerpo = WEB[i:i + 2600]
    assert "if (!d.cuantas)" in cuerpo


def test_el_detalle_se_construye_solo_al_abrirlo():
    """Construir la lista entera en cada visita para dejarla escondida es trabajo tirado en el
    móvil, que es donde se usa esto."""
    i = WEB.index("async function pintaHecho")
    cuerpo = WEB[i:i + 2600]
    assert "det.dataset.puesto" in cuerpo


# ---------------------------------------------------------------- el endpoint

def test_el_endpoint_devuelve_lo_contado():
    """El resumen se calcula en el servidor: es lo único que se mira el 90% de las veces."""
    import ast
    fuente = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for n in ast.walk(arbol):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "api_hecho":
            cuerpo = ast.unparse(n)
            assert "de_hoy" in cuerpo, "el endpoint sigue devolviendo todo el histórico"
            for clave in ("cuantas", "resumen", "dudosas"):
                assert f"'{clave}'" in cuerpo, clave
            return
    raise AssertionError("no existe api_hecho")
