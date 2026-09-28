# -*- coding: utf-8 -*-
"""Lo que Zeno recuerda, y sobre todo lo que NO se inventa.

Casi todo lo que hay aquí protege una misma cosa: que un apunte sea exactamente lo que el operador
dijo, con su fecha y su origen, y que se pueda borrar. Una memoria que el modelo rellena solo acaba
repitiendo como cierto algo que nadie dijo, y eso choca de frente con su regla de hechos
comprobados.
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    """Una memoria limpia en disco de verdad, no simulada: el módulo se apoya en ficheros y un
    doble no probaría ni el append ni el recorte, que es donde puede romperse."""
    monkeypatch.setenv("ZENO_MEMORIA", str(tmp_path / "memoria.jsonl"))
    monkeypatch.setenv("ZENO_HILO_FICHERO", str(tmp_path / "conversacion.jsonl"))
    from servicio import memoria
    return importlib.reload(memoria)


# ---------------------------------------------------------------- reconocer la orden

def test_se_reconoce_lo_que_hay_que_apuntar(mem):
    for frase, esperado in (
            ("recuerda que los martes no publico", "Los martes no publico"),
            ("Recuerda que el arco es de dos mensajes", "El arco es de dos mensajes"),
            ("acuérdate de que GutLyn es mía", "GutLyn es mía"),
            ("apunta que Xrise lleva las ventas", "Xrise lleva las ventas"),
            ("no olvides llamar al gestor", "Llamar al gestor"),
            ("ten en cuenta que el viernes libro", "El viernes libro")):
        assert mem.es_para_recordar(frase) == esperado, frase


def test_una_pregunta_normal_no_se_guarda_como_apunte(mem):
    """Si cualquier frase con la palabra recuerda se apuntara, la memoria se llenaría de preguntas
    y el operador leería sus propias dudas como si fueran decisiones suyas."""
    for frase in ("¿recuerdas lo que te dije ayer?", "no recuerdo el precio",
                  "cuántos DMs tengo hoy", "qué recuerdas de GutLyn", ""):
        assert mem.es_para_recordar(frase) == "", frase


def test_recuerda_a_secas_no_apunta_nada(mem):
    """Sin texto detrás no hay nada que guardar, y un apunte vacío en la pantalla no se puede ni
    entender ni borrar con criterio."""
    assert mem.es_para_recordar("recuerda") == ""
    assert mem.es_para_recordar("recuerda que  ") == ""


def test_se_guardan_las_palabras_del_operador_con_sus_tildes(mem):
    """El reconocimiento ignora tildes para que funcione dictado; lo GUARDADO no puede perderlas."""
    assert mem.es_para_recordar("acuérdate de que la campaña es el 1 de diciembre") == \
        "La campaña es el 1 de diciembre"


# ---------------------------------------------------------------- guardar, leer, olvidar

def test_lo_apuntado_se_lee_con_su_origen_y_su_fecha(mem):
    a = mem.apunta("los arcos son de dos mensajes")
    [leido] = mem.apuntes()
    assert leido["texto"] == "los arcos son de dos mensajes"
    assert leido["origen"] == "dicho"
    assert leido["cuando"] > 0 and leido["id"] == a["id"]


def test_lo_olvidado_desaparece_de_la_lista_y_del_contexto(mem):
    a = mem.apunta("esto estaba mal")
    mem.apunta("esto vale")
    assert mem.olvida(a["id"])
    assert [x["texto"] for x in mem.apuntes()] == ["esto vale"]
    assert "esto estaba mal" not in mem.para_el_contexto()


def test_olvidar_no_reescribe_el_fichero(mem):
    """Se tacha añadiendo una línea. Reescribir el fichero para quitar una es la operación que
    puede dejarlo a medias y llevarse por delante decisiones del operador."""
    a = mem.apunta("uno")
    antes = mem.FICHERO.read_text(encoding="utf-8")
    mem.olvida(a["id"])
    despues = mem.FICHERO.read_text(encoding="utf-8")
    assert despues.startswith(antes), "el fichero se reescribió en vez de crecer"


def test_una_linea_rota_no_se_lleva_las_demas(mem):
    """Un reinicio en mitad de una escritura deja una línea a medias. Si eso tirara el fichero
    entero, se perdería todo lo que el operador pidió recordar."""
    mem.apunta("esto sí")
    with mem.FICHERO.open("a", encoding="utf-8") as f:
        f.write('{"id": "rot')
    mem.apunta("esto también")
    assert sorted(x["texto"] for x in mem.apuntes()) == ["esto sí", "esto también"]


def test_el_contexto_separa_lo_que_dijo_el_de_lo_que_paso(mem):
    """Entre lo dijo él y lo dedujo una acción hay una diferencia que el modelo tiene que ver,
    porque lo segundo se equivoca y lo primero manda."""
    mem.apunta("los martes no publico", origen="dicho")
    mem.apunta("publicó el post de X", origen="hecho")
    texto = mem.para_el_contexto()
    assert texto.index("PEDIDO RECORDAR") < texto.index("los martes no publico")
    assert "DE LO QUE HA PASADO" in texto
    assert texto.index("PEDIDO RECORDAR") < texto.index("DE LO QUE HA PASADO")


def test_sin_apuntes_el_contexto_va_vacio(mem):
    """Una cabecera vacía en el prompt son tokens que se pagan en cada pregunta y una invitación
    a que el modelo rellene el hueco."""
    assert mem.para_el_contexto() == ""


def test_el_contexto_no_crece_sin_fin(mem):
    """Cada apunte viaja en CADA pregunta. Sin tope, la memoria encarece el chat en silencio."""
    for i in range(60):
        mem.apunta(f"apunte {i}")
    assert mem.para_el_contexto().count("\n  - ") <= mem.CUANTOS


def test_un_apunte_no_puede_ser_una_novela(mem):
    """Un texto enorme pegado por error viajaría en cada pregunta durante meses."""
    assert len(mem.apunta("x" * 5000)["texto"]) <= 400


def test_guardar_no_revienta_si_el_disco_no_deja(mem, monkeypatch):
    """Que la memoria falle no puede tumbar lo que se estaba haciendo: el operador vería un error
    después de una acción que sí se hizo."""
    monkeypatch.setattr(mem, "FICHERO", Path("/no/existe/y/no/se/puede/crear/m.jsonl"))
    mem.apunta("da igual")          # no lanza
    monkeypatch.setattr(mem, "HILO", Path("/no/existe/tampoco/c.jsonl"))
    mem.guarda_turno("tu", "hola")  # no lanza


# ---------------------------------------------------------------- el hilo

def test_la_conversacion_sobrevive_a_cerrar_la_aplicacion(mem):
    mem.guarda_turno("tu", "cómo van las ventas")
    mem.guarda_turno("zeno", "cero, la tienda no está conectada")
    assert [t["de"] for t in mem.hilo()] == ["tu", "zeno"], "el orden importa: el modelo lo lee así"
    assert mem.hilo()[-1]["texto"].startswith("cero")


def test_el_hilo_no_crece_sin_fin(mem):
    for i in range(mem.TOPE_HILO + 50):
        mem.guarda_turno("tu", f"turno {i}")
    lineas = mem.HILO.read_text(encoding="utf-8").strip().splitlines()
    assert len(lineas) <= mem.TOPE_HILO
    assert json.loads(lineas[-1])["texto"] == f"turno {mem.TOPE_HILO + 49}", "recortó por el lado malo"


def test_borrar_el_hilo_no_borra_los_apuntes(mem):
    """Son dos cosas distintas: la conversación caduca, un apunte se queda hasta que él lo borre.
    Si empezar de cero se llevara los apuntes, nadie volvería a pulsarlo."""
    mem.apunta("los arcos son de dos")
    mem.guarda_turno("tu", "hola")
    mem.olvida_el_hilo()
    assert mem.hilo() == []
    assert len(mem.apuntes()) == 1


def test_un_turno_vacio_no_se_guarda(mem):
    mem.guarda_turno("tu", "   ")
    assert mem.hilo() == []
