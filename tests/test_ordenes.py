# -*- coding: utf-8 -*-
"""Mandar hacer algo hablando: que se entienda, y sobre todo que NO se entienda de mas.

EL CASO (2026-09-28). El operador eligio que por voz se pueda ejecutar lo reversible y nada mas:
lo que sale al mundo sigue pidiendo el dedo y el PIN, porque una frase mal entendida no puede
publicar en su nombre y un PIN dicho en alto se oye.

Esta es la pieza mas peligrosa de Zeno: decide que se dispara a partir de un texto que ha salido
de un microfono en la calle. Por eso empareja con reglas y no con el modelo, y por eso la mayoria
de estos tests prueban que NO hace algo.

Puros: ni red, ni base, ni un centimo de API.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import ordenes as o  # noqa: E402

TAREA = {"titulo": "Tarea, Reactivar la landing de XSupport tras la presentacion",
         "acciones": [{"etiqueta": "Marcar hecha", "efecto": "cambia_estado",
                       "reversible": True, "coste_api": False}]}
POST = {"titulo": "W5/P16 D35 - Loading: skip it",
        "acciones": [{"etiqueta": "Aprobar y publicar", "efecto": "publica",
                      "reversible": False, "coste_api": False},
                     {"etiqueta": "Regenerar", "efecto": "cambia_estado",
                      "reversible": False, "coste_api": True},
                     {"etiqueta": "Descartar thread", "efecto": "cambia_estado",
                      "reversible": True, "coste_api": False}]}
TODO = [TAREA, POST]


def test_una_orden_clara_se_entiende():
    r = o.empareja("marca hecha la tarea de la landing de XSupport", TODO)
    assert r["estado"] == "vale"
    assert r["cosa"] is TAREA and r["accion"]["etiqueta"] == "Marcar hecha"


def test_una_pregunta_no_es_una_orden():
    """EL PRIMER FILTRO. El dictado casi nunca pone interrogantes, asi que no se puede depender de
    ellos: "tengo que cerrar la tarea de la landing" habla de lo mismo y no manda nada."""
    for pregunta in ("que tengo pendiente hoy",
                     "tengo que cerrar la tarea de la landing",
                     "cuantas tareas me quedan",
                     "puedo marcar hecha la tarea de la landing",
                     "deberia descartar el post de loading",
                     "dime si la tarea de la landing esta hecha"):
        assert o.empareja(pregunta, TODO)["estado"] == "no_es_orden", pregunta


def test_lo_que_publica_no_se_hace_hablando():
    """LA BARRERA QUE PIDIO EL OPERADOR. Aprobar y publicar sale al mundo: por voz, no."""
    r = o.empareja("aprueba el post de loading", TODO)
    # Ni siquiera llega a emparejar, porque "aprobar" no esta entre los verbos que se admiten.
    assert r["estado"] in ("no_es_orden", "no_entiendo", "nada_encaja")
    # Y si alguien añadiera el verbo, la barrera lo para igual:
    assert not o.se_puede_por_voz(POST["acciones"][0])


def test_lo_que_no_se_deshace_no_se_hace_hablando():
    """Regenerar cambia un estado, o sea pasa el primer filtro, y aun asi no vale: no se deshace y
    ademas cuesta dinero. Es el caso que justifica que la barrera sean tres condiciones y no una."""
    assert not o.se_puede_por_voz(POST["acciones"][1])


def test_lo_reversible_y_barato_si():
    assert o.se_puede_por_voz(TAREA["acciones"][0])
    assert o.se_puede_por_voz(POST["acciones"][2])


def test_si_encaja_con_dos_cosas_no_se_hace_ninguna():
    """Acertar la que no era cuesta deshacerlo, y deshacerlo desde el movil es justo lo que se
    venia a evitar. Preguntar cual de las dos cuesta tres segundos."""
    dos = [{"titulo": "Tarea, revisar la landing de XSupport",
            "acciones": [{"etiqueta": "Marcar hecha", "efecto": "cambia_estado",
                          "reversible": True, "coste_api": False}]},
           {"titulo": "Tarea, rehacer la landing de XSupport",
            "acciones": [{"etiqueta": "Marcar hecha", "efecto": "cambia_estado",
                          "reversible": True, "coste_api": False}]}]
    r = o.empareja("marca hecha la landing de XSupport", dos)
    assert r["estado"] == "varias"
    assert len(r["cuales"]) == 2


def test_si_no_hay_nada_parecido_no_se_inventa():
    assert o.empareja("marca hecha la factura de noviembre", TODO)["estado"] == "nada_encaja"


def test_una_orden_sin_objeto_no_coge_la_primera_que_pille():
    """"marca hecha" a secas no dice cual. Coger la primera de la lista seria lo comodo y lo
    peor: cambia segun lo que hubiera ese dia."""
    assert o.empareja("marca hecha", TODO)["estado"] == "nada_encaja"


def test_los_acentos_no_deciden_nada():
    """Lo que sale de un microfono no trae tildes fiables."""
    a = o.empareja("marca hecha la tarea de la presentación", TODO)
    b = o.empareja("marca hecha la tarea de la presentacion", TODO)
    assert a["estado"] == b["estado"] == "vale"


def test_solo_un_si_claro_confirma():
    """LA ASIMETRIA A PROPOSITO. Ante la duda no se ejecuta: un ruido, un carraspeo o media frase
    no pueden valer por un si."""
    for si in ("si", "sí", "vale", "hazlo", "adelante", "claro", "dale", "ok"):
        assert o.dice_que_si(si), si
    for no in ("no", "no, mejor no", "espera", "para", "dejalo", "cancela", "",
               "no lo hagas", "mmm", "que", "repite", "no se", "otra cosa"):
        assert not o.dice_que_si(no), no


def test_un_no_que_lleva_dentro_una_palabra_de_si():
    """"no, vale, dejalo" lleva "vale" dentro. Un `in` mal puesto lo leeria como un si y cerraria
    una tarea que se acababa de rechazar."""
    for trampa in ("no vale", "no, vale, dejalo", "para, si no", "no claro que no"):
        assert not o.dice_que_si(trampa), trampa


def test_la_barrera_no_se_abre_con_un_campo_que_falte():
    """Si una accion llega sin `reversible` (un contrato viejo, un sistema nuevo), la respuesta es
    que NO se puede por voz. Lo que falta no se presume a favor."""
    for incompleta in ({}, {"efecto": "cambia_estado"}, {"reversible": True},
                       {"reversible": True, "efecto": "cambia_estado", "coste_api": True},
                       {"reversible": True, "efecto": "publica"}):
        assert not o.se_puede_por_voz(incompleta), incompleta
