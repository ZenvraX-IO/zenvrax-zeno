# -*- coding: utf-8 -*-
"""La agenda que propone: todo lo que no puede pasar entre pensar una cita y crearla.

EL CASO. Esta es la primera pieza de Zeno que ESCRIBE. Hasta aquí lo peor que podía pasar era
enseñar un dato mal; una cita creada sale al mundo: si lleva invitados les llega un correo que no se
puede recoger, y aunque no los lleve, ocupa un hueco que alguien da por bueno.

El operador eligió sobre tres opciones: *"que proponga, tú confirmas"*. Estos tests son esa
decisión escrita en código, y cubren las seis formas de saltársela sin que se note:

1. Que proponer ya cree la cita.
2. Que se pueda confirmar algo que nadie propuso, o dos veces lo mismo.
3. Que una propuesta vieja abierta en el móvil siga siendo válida horas después.
4. Que los invitados aparezcan al confirmar sin haberse visto en la propuesta.
5. Que se proponga un hueco que no existe: fuera de horario, en fin de semana, o pisando algo.
6. Que un festivo de día completo deje la semana sin un solo hueco.

Puros: sin red. Se sustituye lo que Google devuelve.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import citas, google                    # noqa: E402

#: Un miércoles a las 8 de la mañana, para que el dia de prueba sea laborable y entero por delante.
MIERCOLES = datetime(2026, 10, 7, 8, 0, tzinfo=citas.ZONA)


@pytest.fixture(autouse=True)
def _reloj_quieto(monkeypatch):
    monkeypatch.setattr(citas, "_ahora", lambda: MIERCOLES)
    citas._PROPUESTAS.clear()
    yield
    citas._PROPUESTAS.clear()


def _agenda(monkeypatch, eventos):
    """Lo que devolveria Google. `eventos` son (hora_inicio, hora_fin, titulo) del mismo dia."""
    items = []
    for e in eventos:
        if len(e) == 2 and isinstance(e[0], str):        # dia completo: solo fecha
            items.append({"summary": e[1], "start": {"date": e[0]}, "end": {"date": e[0]}})
            continue
        a, b, t = e
        items.append({"summary": t,
                      "start": {"dateTime": MIERCOLES.replace(hour=a, minute=0).isoformat()},
                      "end": {"dateTime": MIERCOLES.replace(hour=b, minute=0).isoformat()}})
    monkeypatch.setattr(google, "pide", lambda n, url: {"items": items})


def _escritura_prohibida(monkeypatch):
    def no(*a, **k):
        raise AssertionError("se ha escrito en Google sin confirmar")
    monkeypatch.setattr(google, "escribe", no)


# ---------------------------------------------------------------- proponer no crea nada

def test_proponer_no_toca_google(monkeypatch):
    """EL TEST QUE IMPORTA. Si proponer creara la cita, la decision del operador de confirmar antes
    no serviria de nada: ya existiria cuando la ve."""
    _agenda(monkeypatch, [])
    _escritura_prohibida(monkeypatch)
    p = citas.propone("zenvrax", "Llamada", (MIERCOLES + timedelta(hours=2)).isoformat())
    assert p["vale"] and p["titulo"] == "Llamada"


def test_confirmar_sin_vale_no_crea_nada(monkeypatch):
    _escritura_prohibida(monkeypatch)
    with pytest.raises(citas.NoSePuede):
        citas.confirma("inventado")


def test_un_vale_sirve_una_sola_vez(monkeypatch):
    """Pulsar dos veces el boton, o volver atras en el movil, crearia la cita duplicada."""
    _agenda(monkeypatch, [])
    creadas = []
    monkeypatch.setattr(google, "escribe",
                        lambda n, u, c, metodo="POST": creadas.append(c) or {"id": "1"})
    v = citas.propone("zenvrax", "Llamada", (MIERCOLES + timedelta(hours=2)).isoformat())["vale"]
    citas.confirma(v)
    with pytest.raises(citas.NoSePuede):
        citas.confirma(v)
    assert len(creadas) == 1


def test_una_propuesta_vieja_caduca(monkeypatch):
    """Una pantalla abierta desde ayer en el movil no puede crear una cita al pulsar: el hueco que
    calculo ya no tiene por que estar libre."""
    _agenda(monkeypatch, [])
    _escritura_prohibida(monkeypatch)
    v = citas.propone("zenvrax", "Llamada", (MIERCOLES + timedelta(hours=2)).isoformat())["vale"]
    citas._PROPUESTAS[v]["nacida"] = 0.0                 # nacida en 1970
    with pytest.raises(citas.NoSePuede) as e:
        citas.confirma(v)
    assert "caducado" in str(e.value)


def test_la_propuesta_dice_si_va_a_avisar_a_alguien(monkeypatch):
    """Lo que no se deshace es el correo al invitado. Tiene que verse ANTES de confirmar, no
    descubrirse despues en la respuesta."""
    _agenda(monkeypatch, [])
    sola = citas.propone("zenvrax", "Pensar", (MIERCOLES + timedelta(hours=2)).isoformat())
    assert sola["avisa_a_invitados"] is False
    con = citas.propone("zenvrax", "Reunion", (MIERCOLES + timedelta(hours=3)).isoformat(),
                        con=["alguien@cliente.com"])
    assert con["avisa_a_invitados"] is True and con["con"] == ["alguien@cliente.com"]


def test_solo_se_avisa_a_invitados_si_los_hay(monkeypatch):
    """`sendUpdates` es el parametro que decide si SALE un correo. Con "all" siempre, una cita
    para uno mismo no manda nada hoy, pero el dia que Google cambie eso manda correos solo."""
    _agenda(monkeypatch, [])
    urls = []
    monkeypatch.setattr(google, "escribe",
                        lambda n, u, c, metodo="POST": urls.append(u) or {"id": "1"})
    v = citas.propone("zenvrax", "Pensar", (MIERCOLES + timedelta(hours=2)).isoformat())["vale"]
    citas.confirma(v)
    assert "sendUpdates=none" in urls[0]

    v = citas.propone("zenvrax", "Reunion", (MIERCOLES + timedelta(hours=3)).isoformat(),
                      con=["a@b.com"])["vale"]
    citas.confirma(v)
    assert "sendUpdates=all" in urls[1]


def test_no_se_propone_una_cita_en_el_pasado(monkeypatch):
    _agenda(monkeypatch, [])
    with pytest.raises(citas.NoSePuede):
        citas.propone("zenvrax", "Tarde", (MIERCOLES - timedelta(hours=1)).isoformat())


def test_una_cita_sin_titulo_no_se_propone(monkeypatch):
    _agenda(monkeypatch, [])
    with pytest.raises(citas.NoSePuede):
        citas.propone("zenvrax", "   ", (MIERCOLES + timedelta(hours=2)).isoformat())


# ---------------------------------------------------------------- los huecos son de verdad

def test_los_huecos_caen_dentro_del_horario(monkeypatch):
    """Un hueco a las tres de la mañana es un hueco y no sirve de nada."""
    _agenda(monkeypatch, [])
    for h in citas.huecos("zenvrax", minutos=30, dias=5, cuantos=8):
        d = datetime.fromisoformat(h["desde"])
        assert citas.ABRE <= d.hour < citas.CIERRA, f"hueco fuera de horario: {h['etiqueta']}"
        assert d.weekday() in citas.LABORABLES, f"hueco en fin de semana: {h['etiqueta']}"


def test_un_hueco_no_pisa_lo_que_ya_hay(monkeypatch):
    """Con el colchon puesto: dos reuniones pegadas no son dos huecos reales."""
    _agenda(monkeypatch, [(10, 11, "Reunion"), (12, 13, "Otra")])
    for h in citas.huecos("zenvrax", minutos=30, dias=1, cuantos=8):
        a = datetime.fromisoformat(h["desde"])
        b = datetime.fromisoformat(h["hasta"])
        for ha, hb in ((10, 11), (12, 13)):
            ocupado_a = MIERCOLES.replace(hour=ha)
            ocupado_b = MIERCOLES.replace(hour=hb)
            assert not (a < ocupado_b and b > ocupado_a), f"el hueco pisa {ha}-{hb}"


def test_un_festivo_de_dia_completo_no_borra_los_huecos(monkeypatch):
    """PASA DE VERDAD con el calendario de Festivos en España, que Google devuelve como evento de
    dia completo. Contarlo como ocupado dejaba semanas enteras sin un solo hueco."""
    _agenda(monkeypatch, [("2026-10-07", "Festivo")])
    assert citas.huecos("zenvrax", minutos=30, dias=1), "un festivo no impide una llamada"


def test_una_reunion_rechazada_deja_su_hora_libre(monkeypatch):
    """Si dijiste que no, esa hora esta libre. Bloquearla es perder huecos por reuniones a las que
    ni siquiera vas."""
    monkeypatch.setattr(google, "pide", lambda n, url: {"items": [{
        "summary": "A la que dije que no",
        "start": {"dateTime": MIERCOLES.replace(hour=10).isoformat()},
        "end": {"dateTime": MIERCOLES.replace(hour=14).isoformat()},
        "attendees": [{"self": True, "responseStatus": "declined"}]}]})
    huecos = citas.huecos("zenvrax", minutos=30, dias=1, cuantos=3)
    assert any(datetime.fromisoformat(h["desde"]).hour in range(10, 14) for h in huecos)


def test_una_cita_cancelada_no_ocupa(monkeypatch):
    monkeypatch.setattr(google, "pide", lambda n, url: {"items": [{
        "summary": "Cancelada", "status": "cancelled",
        "start": {"dateTime": MIERCOLES.replace(hour=9).isoformat()},
        "end": {"dateTime": MIERCOLES.replace(hour=18).isoformat()}}]})
    assert citas.huecos("zenvrax", minutos=30, dias=1)


def test_el_hueco_se_dice_como_lo_diria_una_persona(monkeypatch):
    """"2026-10-08T10:00:00+02:00" no se lee de un vistazo en un movil."""
    _agenda(monkeypatch, [])
    h = citas.huecos("zenvrax", minutos=45, dias=3, cuantos=1)[0]
    assert "a las" in h["etiqueta"] and "45 min" in h["etiqueta"]
    assert "hoy" in h["etiqueta"] or "mañana" in h["etiqueta"] or "el " in h["etiqueta"]


# ---------------------------------------------------------------- los choques

def test_dos_citas_que_se_pisan_salen_como_choque(monkeypatch):
    _agenda(monkeypatch, [(10, 12, "Una"), (11, 13, "La otra")])
    c = citas.choques("zenvrax")
    assert len(c) == 1 and c[0]["uno"] == "Una" and c[0]["otro"] == "La otra"


def test_dos_citas_seguidas_no_son_un_choque(monkeypatch):
    """Avisar de dos reuniones pegadas convertiria el aviso en ruido, y un aviso que se ignora es
    peor que no tenerlo."""
    _agenda(monkeypatch, [(10, 11, "Una"), (11, 12, "La siguiente")])
    assert citas.choques("zenvrax") == []


def test_un_rato_libre_ofrece_varias_horas_no_solo_la_primera(monkeypatch):
    """LO ENCONTRO ESTE FICHERO. Con la agenda vacia, `huecos` devolvia UN hueco por dia, el de
    primera hora: "a las nueve o nada" no es una propuesta. Ahora se ofrecen varios por rato libre,
    cada media hora."""
    _agenda(monkeypatch, [])
    h = citas.huecos("zenvrax", minutos=30, dias=1, cuantos=6)
    horas = sorted({datetime.fromisoformat(x["desde"]).strftime("%H:%M") for x in h})
    assert len(horas) >= 4, f"solo se ofrecen {horas}"
    assert horas[0] == "09:00"


def test_los_huecos_caen_en_hora_redonda(monkeypatch):
    """Nadie queda a las 09:07. Un hueco con minutos sueltos no se lee como una opcion, se lee como
    un calculo."""
    monkeypatch.setattr(citas, "_ahora", lambda: MIERCOLES.replace(hour=10, minute=7))
    _agenda(monkeypatch, [])
    for x in citas.huecos("zenvrax", minutos=30, dias=1, cuantos=4):
        assert datetime.fromisoformat(x["desde"]).minute in (0, 30), x["etiqueta"]
