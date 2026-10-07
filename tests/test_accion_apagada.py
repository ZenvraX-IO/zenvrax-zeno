# -*- coding: utf-8 -*-
"""Una accion APAGADA se ve, dice por que, y no se dispara.

POR QUE EXISTE (2026-10-07). El boton de minar se hizo primero para que apareciera solo cuando
tocaba, y el mismo dia el operador pregunto *"pero donde estaria lo de minar el engager desde
Zeno? No lo veo"*: estaba oculto porque ese dia ya se habia minado, y la unica forma de saberlo
era leer el codigo. Su decision: *"deberia ser algo parecido a que estuviera siempre y tan solo
se activara el boton de minar cuando sea requerido y sea necesario. Y mientras ya este minado o
barrido, ese boton permanezca desactivado"*.

Las tres pruebas van con el fallo dentro: si alguien quita el filtro del emparejador o deja de
propagar el campo, esto se pone rojo.
"""
import re
import pathlib

import lector

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _accion(**kw):
    """Una accion de cola tal como la manda el cockpit."""
    base = {"patch": {"path": "/marketing/linkedin/sync-request", "verb": "POST",
                      "body": {"kind": "minar"}},
            "label": "⛏️ Minar ahora"}
    base.update(kw)
    return base


def test_el_lector_recoge_que_esta_apagada_y_por_que():
    acciones = lector._acciones("cockpit",
                                [_accion(disabled=True,
                                         disabled_reason="hoy ya se han minado 3 contactos")],
                                lector._indice_del_catalogo())
    assert len(acciones) == 1
    a = acciones[0]
    assert a.bloqueada is True
    assert a.motivo_bloqueo == "hoy ya se han minado 3 contactos"


def test_sin_la_marca_la_accion_sigue_encendida():
    """El campo es nuevo: los avisos que no lo traen NO pueden quedarse apagados por omision."""
    a = lector._acciones("cockpit", [_accion()], lector._indice_del_catalogo())[0]
    assert a.bloqueada is False
    assert a.motivo_bloqueo == ""


def test_la_pantalla_pinta_la_apagada_sin_enganchar_el_pulsador():
    """En gris, con el motivo, y SIN `data-hacer` ni `data-aviso`: pulsarla no hace nada.

    Se lee el fichero porque la pantalla no tiene tests de navegador: lo que se comprueba es que
    las dos puertas por las que salen botones miran `bloqueada` antes de poner el enganche.
    """
    html = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
    # Puerta 1: pintaAccion, la de las colas de aprobacion.
    pinta = html[html.index("function pintaAccion"):]
    pinta = pinta[:pinta.index("\n}")]
    # Sin comentarios: dentro de ellos se NOMBRA `data-hacer` para explicar que el boton apagado
    # no lo lleva, y comparar posiciones sobre el texto crudo tomaba esa mencion por el enganche.
    codigo = re.sub(r"//.*", "", pinta)
    assert "a.bloqueada" in codigo, "pintaAccion no mira si la accion esta apagada"
    assert codigo.index("a.bloqueada") < codigo.index("data-hacer"), \
        "mira lo apagado DESPUES de poner el enganche: el boton seguiria siendo pulsable"
    # Puerta 2: la lista de avisos sueltos.
    assert re.search(r"ac\.bloqueada[\s\S]{0,400}data-aviso", html), \
        "la lista de avisos no mira si la accion esta apagada antes de enganchar el pulsador"
    assert "b apagada" in html and "porque-apagada" in html


def test_la_voz_no_puede_disparar_lo_que_esta_apagado():
    """El emparejador recibe la lista YA filtrada: una frase no enciende un boton en gris."""
    api = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")
    trozo = api[api.index("Las dos listas juntas"):]
    trozo = trozo[:trozo.index("ordenes.empareja")]
    assert "if not a.bloqueada" in trozo, \
        "la lista que ve el emparejador de voz no filtra las acciones apagadas"
