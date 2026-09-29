# -*- coding: utf-8 -*-
"""El correo, separado por negocio: Zenvrax por un lado y GutLyn por otro.

EL CASO (2026-09-29). El operador, sobre la pestaña Personal: *"los email, ¿puedes tener un
desplegable por Zenvrax y otro por GutLyn? O separarlos de alguna manera"*.

Ya existía un filtro por negocio, y estaba escondido SIEMPRE: el correo de GutLyn llega al mismo
buzón como alias, la consulta traía los doce sin leer más recientes, y medido ese día había 50 sin
leer en siete días con solo UNO de GutLyn. Así que el filtro veía un único negocio y se ocultaba.

Dos cosas se arreglan a la vez: cada negocio pide los SUYOS (en `personal.py`), y aquí se agrupan
en secciones en lugar de un filtro que hay que tocar para ver lo del otro.
"""
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- el filtro de la consulta

@pytest.fixture()
def per():
    from servicio import personal
    return importlib.reload(personal)


def test_cada_negocio_pide_lo_suyo(per, monkeypatch):
    """LA BARRERA. Con una sola consulta y reparto posterior, el negocio que recibe poco correo
    desaparece detrás del recorte y su grupo sale vacío SIN ESTARLO."""
    from servicio import google
    monkeypatch.setattr(google, "CUENTAS", {"zenvrax": "a@zenvrax.com"})
    monkeypatch.setattr(google, "ALIAS", {"gutlyn": "b@gutlyn.com"})
    negocios = ["zenvrax", "gutlyn"]
    del_alias = per._filtro_del_negocio("gutlyn", negocios)
    del_dueno = per._filtro_del_negocio("zenvrax", negocios)
    assert "gutlyn.com" in del_alias and "to:" in del_alias
    # El dueño se lleva TODO lo que no es del alias, no una lista de sus dominios: un correo a una
    # dirección que nadie declaró tiene que salir en algún sitio.
    assert del_dueno == "-to:gutlyn.com -cc:gutlyn.com", del_dueno


def test_sin_alias_declarados_no_se_filtra_nada(per, monkeypatch):
    """Con un solo negocio, meter un filtro vacío o mal formado en la consulta la rompería o
    dejaría la bandeja a cero."""
    from servicio import google
    monkeypatch.setattr(google, "CUENTAS", {"zenvrax": "a@zenvrax.com"})
    monkeypatch.setattr(google, "ALIAS", {})
    assert per._filtro_del_negocio("zenvrax", ["zenvrax"]) == ""


def test_un_correo_no_puede_salir_dos_veces(per, monkeypatch):
    """Preguntar dos veces al MISMO buzón es lo que abre esta puerta. Si un correo va dirigido a
    los dos negocios, o si un filtro fallara, saldría repetido: es el duplicado de septiembre
    volviendo por otro camino."""
    from servicio import google
    monkeypatch.setattr(google, "conectadas", lambda: {
        "zenvrax": {"cuenta": "a@zenvrax.com", "buzon": "a@zenvrax.com"}})
    monkeypatch.setattr(google, "CUENTAS", {"zenvrax": "a@zenvrax.com"})
    monkeypatch.setattr(google, "ALIAS", {"gutlyn": "b@gutlyn.com"})
    # El mismo correo contestado a las DOS consultas: el peor caso posible.
    monkeypatch.setattr(per, "correos",
                        lambda n, **k: [{"id": "m1", "asunto": "uno", "negocio": "zenvrax"}])
    monkeypatch.setattr(per, "agenda", lambda n, **k: [])
    datos, _ = per.bandeja()
    assert len(datos["correos"]) == 1, datos["correos"]


# ---------------------------------------------------------------- la pantalla

def test_un_negocio_sin_correo_no_desaparece():
    """LO QUE MÁS IMPORTA AQUÍ. Si GutLyn se cayera de la pantalla los días que no tiene nada, el
    operador no sabría si es que no hay correo o que no se está mirando, que es exactamente la
    duda de la que salió este trabajo."""
    i = WEB.index("function pintaCorreos")
    cuerpo = WEB[i:i + 2400]
    assert "negociosDelCorreo" in cuerpo, "los grupos salen de lo que HAY, no de lo que existe"
    assert "nada sin leer de" in cuerpo, "un negocio vacío no dice que está vacío"


def test_los_grupos_salen_de_los_buzones_conectados():
    """Y no de los correos que hayan llegado hoy: esa es la diferencia entre "no hay nada de
    GutLyn" y "GutLyn no se está mirando"."""
    i = WEB.index("correosEnPantalla = datos.correos")
    cuerpo = WEB[i:i + 800]
    assert "datos.buzones" in cuerpo and "b.negocios" in cuerpo


def test_el_hueco_del_borrador_es_uno_solo():
    """Con un `<div id="borrador">` por grupo, `$("#borrador")` cogería el primero y la respuesta
    aparecería en el grupo equivocado."""
    assert WEB.count('id="borrador"') == 1, "hay más de un hueco de borrador"


def test_el_filtro_viejo_no_se_queda_a_medias():
    """Dejar la variable del filtro sin usar invita a volver a usarla, y entonces conviven dos
    formas de separar lo mismo."""
    assert "filtroNegocio" not in WEB, "queda el filtro viejo por ahí"
    assert 'id="filtros"' not in WEB


def test_con_un_solo_negocio_no_se_agrupa():
    """Una cabecera "zenvrax" sobre la única lista que hay es una fila gastada en la pantalla que
    más se mira."""
    i = WEB.index("function pintaCorreos")
    cuerpo = WEB[i:i + 2400]
    assert "grupos.length < 2" in cuerpo


# ---------------------------------------------------------------- lo que el front necesita

def test_el_endpoint_manda_lo_que_la_pantalla_pide():
    """EL FALLO QUE VIO EL MÓVIL Y NO LOS OCHO TESTS (2026-09-29).

    La pantalla agrupa por `datos.buzones`, y `/api/personal` no lo devolvía: `bandeja()` lo
    construía y se quedaba dentro. Resultado: cero grupos en producción con todo en verde, porque
    ninguna prueba miraba que la respuesta trajera lo que el front consume.

    Se cruzan las dos listas en vez de comprobar una clave suelta: así también salta el día que el
    front empiece a usar algo nuevo.
    """
    import ast
    import re

    fuente = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    devuelve = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "api_personal":
            for sub in ast.walk(n):
                if isinstance(sub, ast.Dict):
                    devuelve |= {k.value for k in sub.keys
                                 if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert devuelve, "no encuentro lo que devuelve api_personal"

    # Lo que la pantalla lee de esa respuesta, tal cual está escrito en el front.
    i = WEB.index("async function cargaPersonal")
    pantalla = WEB[i:i + 4000]
    pide = set(re.findall(r"\bdatos\.(\w+)", pantalla))
    faltan = sorted(pide - devuelve)
    assert not faltan, f"la pantalla lee {faltan} y el endpoint no lo manda"
