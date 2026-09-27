# -*- coding: utf-8 -*-
"""Cuándo Zeno puede interrumpirte, y sobre todo cuándo no.

EL CASO. Esta es la primera pieza que habla sin que nadie la abra, y eso la hace distinta de todo lo
demás: un aviso de más no molesta un poco, rompe el sistema entero. En cuanto suenan dos que no
hacían falta se dejan de mirar los que sí, y entonces tener avisos es peor que no tenerlos.

Esta casa ya tiene tres reglas escritas sobre esto, de tres incidentes distintos: una alerta que
solo debe sonar una vez necesita clave fija, un aviso por semana y no la cola entera, y una alerta
sin hora se lee como si fuera de ahora. Estos tests son esas reglas convertidas en código.

Las seis formas de romperlo:

1. Que lo mismo suene cada día porque la clave lleva el número dentro.
2. Que diez cosas nuevas sean diez avisos en vez de uno.
3. Que un fallo en bucle mande cincuenta avisos en una tarde.
4. Que algo que empeora de verdad se calle por haber sonado ya.
5. Que un fichero de estado a medias deje a Zeno mudo.
6. Que el mismo móvil suscrito dos veces reciba todo por duplicado.

Puros: sin red y sin navegador.
"""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import avisos                            # noqa: E402

AHORA = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _casa_limpia(monkeypatch, tmp_path):
    monkeypatch.setattr(avisos, "CASA", tmp_path / "avisos.json")
    yield


def _urgente(titulo, clave=None, grave=False, valor=None):
    return {"tipo": "urgente", "negocio": "Zenvrax IO", "titulo": titulo,
            "clave": clave, "grave": grave, "valor": valor}


# ---------------------------------------------------------------- una clave suena una vez

def test_lo_mismo_no_suena_dos_veces():
    """La regla de la casa: una alerta que solo debe sonar una vez necesita clave fija. Sin esto,
    la tarea urgente que lleva tres semanas ahi avisa cada vez que se mira."""
    c = [_urgente("Landing de XSupport sin enlaces", clave="tarea-77")]
    suenan, _ = avisos.que_suena(c, ahora=AHORA)
    assert len(suenan) == 1
    otra_vez, _ = avisos.que_suena(c, ahora=AHORA + 3600)
    assert otra_vez == [], "ha vuelto a sonar lo mismo"


def test_la_clave_no_lleva_el_numero_dentro():
    """EL FALLO CLASICO. Si la clave fuera "57 signups", manaña con 58 seria un aviso nuevo y
    sonaria todos los dias hasta que el numero dejara de moverse."""
    hoy = {"tipo": "alerta", "negocio": "GutLyn+", "clave": "waitlist",
           "titulo": "Signups sin contactar: 57", "valor": 57}
    manana = {**hoy, "titulo": "Signups sin contactar: 58", "valor": 58}
    assert avisos._clave(hoy) == avisos._clave(manana)
    avisos.que_suena([hoy], ahora=AHORA)
    suenan, _ = avisos.que_suena([manana], ahora=AHORA + 86400)
    assert suenan == [], "un temblor del numero no es noticia"


def test_si_empeora_de_verdad_vuelve_a_sonar():
    """Y AL REVES, que es la otra mitad. Callarse siempre convierte el aviso en un adorno: 57
    signups sin contactar es rutina, 90 es que algo ha cambiado."""
    poco = {"tipo": "alerta", "clave": "waitlist", "titulo": "Signups: 57", "valor": 57}
    mucho = {**poco, "titulo": "Signups: 90", "valor": 90}
    avisos.que_suena([poco], ahora=AHORA)
    suenan, _ = avisos.que_suena([mucho], ahora=AHORA + 86400)
    assert len(suenan) == 1


def test_lo_que_se_pone_grave_suena_aunque_ya_sonara_en_ambar():
    """Un aviso que pasa de ambar a rojo es informacion nueva, no la misma de antes."""
    ambar = _urgente("Beneficio del mes", clave="pnl", grave=False)
    rojo = _urgente("Beneficio del mes en negativo", clave="pnl", grave=True)
    avisos.que_suena([ambar], ahora=AHORA)
    suenan, _ = avisos.que_suena([rojo], ahora=AHORA + 600)
    assert len(suenan) == 1


def test_pasados_tres_dias_vuelve_a_sonar():
    """Un silencio eterno esconde algo que vuelve. Tres dias es lo bastante para no repetir una
    tarea que sigue ahi, y poco para que algo que reaparece la semana que viene avise."""
    c = [_urgente("Algo", clave="x")]
    avisos.que_suena(c, ahora=AHORA)
    assert avisos.que_suena(c, ahora=AHORA + avisos.SILENCIO - 10)[0] == []
    assert len(avisos.que_suena(c, ahora=AHORA + avisos.SILENCIO + 10)[0]) == 1


# ---------------------------------------------------------------- no se acumulan

def test_diez_cosas_nuevas_son_un_solo_aviso():
    """La regla de la casa: un aviso por semana, no la cola entera. Diez notificaciones seguidas en
    el movil se descartan todas de un gesto, incluida la que importaba."""
    suenan, _ = avisos.que_suena([_urgente(f"Cosa {i}", clave=f"c{i}") for i in range(10)],
                                 ahora=AHORA)
    assert len(suenan) == 10
    m = avisos.redacta(suenan)
    assert "10" in m["titulo"], m["titulo"]
    assert "y 7 mas" in m["cuerpo"], m["cuerpo"]


def test_un_solo_aviso_dice_lo_que_es():
    m = avisos.redacta([_urgente("Responder a Era Emre", clave="dm")])
    assert m["cuerpo"] == "Responder a Era Emre"
    assert "mal" not in m["titulo"]


def test_lo_grave_se_ve_en_el_titulo():
    """El titulo es lo unico que se lee en la pantalla bloqueada del movil."""
    m = avisos.redacta([_urgente("Beneficio negativo", clave="a", grave=True),
                        _urgente("Otra cosa", clave="b")])
    assert "grave" in m["titulo"]


def test_hay_un_tope_diario_de_envios():
    """La ultima red. Si algo se rompe y empieza a generar avisos, el operador recibe cinco y no
    cincuenta: un movil que vibra treinta veces se silencia, y entonces no avisa de nada."""
    for i in range(avisos.TOPE_DIARIO):
        suenan, _ = avisos.que_suena([_urgente(f"Cosa {i}", clave=f"k{i}")], ahora=AHORA + i)
        assert len(suenan) == 1
    pasado, _ = avisos.que_suena([_urgente("Una mas", clave="extra")], ahora=AHORA + 100)
    assert pasado == [], "se ha pasado del tope diario"


def test_lo_que_no_sono_por_el_tope_no_llega_de_golpe_manana():
    """Si lo callado quedara pendiente, al dia siguiente sonaria el atasco entero."""
    for i in range(avisos.TOPE_DIARIO + 3):
        avisos.que_suena([_urgente(f"Cosa {i}", clave=f"k{i}")], ahora=AHORA + i)
    manana, _ = avisos.que_suena([_urgente("Cosa 6", clave="k6")], ahora=AHORA + 90000)
    assert manana == [], "ha vuelto el atasco de ayer"


# ---------------------------------------------------------------- el estado aguanta

def test_un_fichero_a_medias_no_deja_a_zeno_mudo(monkeypatch, tmp_path):
    """Un JSON cortado a la mitad por un reinicio no puede apagar los avisos. Como mucho suena otra
    vez algo de ayer, que es mucho menos malo que quedarse callado."""
    roto = tmp_path / "avisos.json"
    roto.write_text('{"suscripciones": [', encoding="utf-8")
    monkeypatch.setattr(avisos, "CASA", roto)
    suenan, _ = avisos.que_suena([_urgente("Algo", clave="x")], ahora=AHORA)
    assert len(suenan) == 1


def test_el_mismo_movil_no_se_suscribe_dos_veces():
    """Suscrito dos veces, cada aviso llegaria por duplicado, que es la forma mas rapida de que se
    apaguen las notificaciones."""
    s = {"endpoint": "https://push/abc", "keys": {"p256dh": "x", "auth": "y"}}
    assert avisos.apunta(s) == 1
    assert avisos.apunta({**s, "keys": {"p256dh": "z", "auth": "w"}}) == 1
    assert avisos.suscritos() == 1


def test_una_suscripcion_sin_endpoint_se_rechaza():
    with pytest.raises(ValueError):
        avisos.apunta({"keys": {}})


def test_se_puede_dejar_de_recibir():
    avisos.apunta({"endpoint": "https://push/abc"})
    assert avisos.olvida("https://push/abc") is True
    assert avisos.suscritos() == 0


def test_el_estado_sobrevive_al_reinicio(monkeypatch, tmp_path):
    """En memoria, cada despliegue de Zeno haria sonar de nuevo todo lo de la semana."""
    casa = tmp_path / "avisos.json"
    monkeypatch.setattr(avisos, "CASA", casa)
    avisos.que_suena([_urgente("Algo", clave="x")], ahora=AHORA)
    assert "x" in json.dumps(json.loads(casa.read_text(encoding="utf-8")))
    otra_vez, _ = avisos.que_suena([_urgente("Algo", clave="x")], ahora=AHORA + 60)
    assert otra_vez == []
