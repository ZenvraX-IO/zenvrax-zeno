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


# ---------------------------------------------------------------- los invitados salen al mundo

def test_un_correo_mal_escrito_no_crea_la_cita(monkeypatch):
    """Invitar SALE AL MUNDO: Google manda un correo a cada direccion de la lista. Una errata no da
    error, crea la cita e invita a otra persona.

    Importa mas con voz, que es para lo que el operador lo pidio: una direccion mal entendida es lo
    normal, no la excepcion. Mejor que Zeno diga "no te he entendido el correo" a que invite a un
    desconocido y el correo ya no se pueda recoger.
    """
    _agenda(monkeypatch, [])
    _escritura_prohibida(monkeypatch)
    cuando = (MIERCOLES + timedelta(hours=2)).isoformat()
    for malo in ("alguien arroba cliente.com", "alguien@", "@cliente.com", "alguien@cliente",
                 "uno@a.com dos@b.com"):
        with pytest.raises(citas.NoSePuede) as e:
            citas.propone("zenvrax", "Reunion", cuando, con=[malo])
        assert "no parece un correo" in str(e.value)


def test_los_invitados_se_limpian_y_no_se_repiten(monkeypatch):
    """Dictado o copiado, un correo llega con corchetes, con una coma pegada o dos veces. Invitar
    dos veces al mismo manda dos correos."""
    _agenda(monkeypatch, [])
    p = citas.propone("zenvrax", "Reunion", (MIERCOLES + timedelta(hours=2)).isoformat(),
                      con=[" <uno@cliente.com> ", "uno@cliente.com,", "UNO@cliente.com", "",
                           "dos@cliente.com."])
    assert p["con"] == ["uno@cliente.com", "dos@cliente.com"]


def test_con_invitados_la_propuesta_avisa_antes_de_confirmar(monkeypatch):
    """Ya estaba, pero ahora que el campo existe en la pantalla es la unica barrera entre escribir
    un correo y que le llegue la invitacion."""
    _agenda(monkeypatch, [])
    p = citas.propone("zenvrax", "Reunion", (MIERCOLES + timedelta(hours=2)).isoformat(),
                      con=["alguien@cliente.com"])
    assert p["avisa_a_invitados"] is True
    assert p["con"] == ["alguien@cliente.com"]


# ---------------------------------------------------------------- mover y cancelar

def _hay_cita(monkeypatch, invitados=(), dia_entero=False):
    inicio = ({"date": "2026-10-07"} if dia_entero
              else {"dateTime": MIERCOLES.replace(hour=11).isoformat()})
    fin = ({"date": "2026-10-08"} if dia_entero
           else {"dateTime": MIERCOLES.replace(hour=12).isoformat()})
    monkeypatch.setattr(google, "pide", lambda n, url: {
        "id": "abc", "summary": "Reunion con el cliente", "start": inicio, "end": fin,
        "attendees": ([{"email": "yo@zenvrax.com", "self": True}] +
                      [{"email": c} for c in invitados]) if invitados else []})


def test_proponer_mover_no_mueve_nada(monkeypatch):
    _hay_cita(monkeypatch)
    _escritura_prohibida(monkeypatch)
    p = citas.propone_cambio("zenvrax", "abc", (MIERCOLES + timedelta(hours=6)).isoformat())
    assert p["que"] == "mover" and p["antes"] and p["cuando"] != p["antes"]


def test_proponer_cancelar_no_cancela_nada(monkeypatch):
    _hay_cita(monkeypatch)
    _escritura_prohibida(monkeypatch)
    p = citas.propone_baja("zenvrax", "abc")
    assert p["que"] == "cancelar" and p["sin_vuelta"] is True


def test_cancelar_una_cita_con_invitados_pide_pin(monkeypatch):
    """EL TEST QUE IMPORTA de esta parte. Cancelar con invitados les manda un correo diciendo que
    la reunion se ha anulado, y ese correo no se recoge. Es el mismo peso que publicar."""
    _hay_cita(monkeypatch, invitados=["cliente@empresa.com"])
    _escritura_prohibida(monkeypatch)
    v = citas.propone_baja("zenvrax", "abc")
    assert v["avisa_a_invitados"] is True
    with pytest.raises(citas.NoSePuede) as e:
        citas.confirma_cambio(v["vale"], pin_abierto=False)
    assert "PIN" in str(e.value)


def test_el_vale_sobrevive_a_un_pin_que_falta(monkeypatch):
    """Si se quemara, habria que rehacer la propuesta cada vez, y eso empuja a dejar el PIN abierto
    siempre, que es justo lo que se quiere evitar."""
    _hay_cita(monkeypatch, invitados=["cliente@empresa.com"])
    hecho = []
    monkeypatch.setattr(google, "escribe",
                        lambda n, u, c, metodo="POST": hecho.append((u, metodo)) or {})
    v = citas.propone_baja("zenvrax", "abc")["vale"]
    with pytest.raises(citas.NoSePuede):
        citas.confirma_cambio(v, pin_abierto=False)
    citas.confirma_cambio(v, pin_abierto=True)
    assert hecho[0][1] == "DELETE" and "sendUpdates=all" in hecho[0][0]


def test_una_cita_sin_invitados_no_pide_pin(monkeypatch):
    """No sale al mundo: solo cambia el calendario de uno mismo, y se deshace volviendo a moverla."""
    _hay_cita(monkeypatch)
    hecho = []
    monkeypatch.setattr(google, "escribe",
                        lambda n, u, c, metodo="POST": hecho.append((u, metodo, c)) or {})
    v = citas.propone_cambio("zenvrax", "abc", (MIERCOLES + timedelta(hours=6)).isoformat())["vale"]
    citas.confirma_cambio(v, pin_abierto=False)
    assert hecho[0][1] == "PATCH" and "sendUpdates=none" in hecho[0][0]


def test_mover_conserva_lo_que_duraba(monkeypatch):
    """Una reunion de una hora movida no puede convertirse en media sin que nadie lo pida."""
    _hay_cita(monkeypatch)
    hecho = []
    monkeypatch.setattr(google, "escribe",
                        lambda n, u, c, metodo="POST": hecho.append(c) or {})
    v = citas.propone_cambio("zenvrax", "abc", (MIERCOLES + timedelta(hours=6)).isoformat())["vale"]
    citas.confirma_cambio(v, pin_abierto=True)
    a = datetime.fromisoformat(hecho[0]["start"]["dateTime"])
    b = datetime.fromisoformat(hecho[0]["end"]["dateTime"])
    assert (b - a) == timedelta(hours=1)


def test_una_cita_de_dia_entero_no_se_mueve_a_medias(monkeypatch):
    """No tiene hora que mover. Tratarla como si la tuviera la convertiria en una cita corta."""
    _hay_cita(monkeypatch, dia_entero=True)
    _escritura_prohibida(monkeypatch)
    with pytest.raises(citas.NoSePuede) as e:
        citas.propone_cambio("zenvrax", "abc", (MIERCOLES + timedelta(hours=6)).isoformat())
    assert "dia entero" in str(e.value)


def test_un_vale_de_crear_no_sirve_para_cancelar(monkeypatch):
    """Los dos flujos comparten el almacen de propuestas. Si se confundieran, confirmar una cita
    nueva podria acabar borrando otra."""
    _agenda(monkeypatch, [])
    v = citas.propone("zenvrax", "Nueva", (MIERCOLES + timedelta(hours=2)).isoformat())["vale"]
    with pytest.raises(citas.NoSePuede):
        citas.confirma_cambio(v, pin_abierto=True)


def test_un_vale_de_cancelar_no_sirve_para_crear(monkeypatch):
    """El caso simetrico del anterior, y el peor de los dos: sin la comprobacion, un vale de
    cancelar metido en el confirmar de crear armaba una cita a medias y devolvia "creada", asi que
    el operador leia que estaba hecho cuando no se habia cancelado nada."""
    _hay_cita(monkeypatch)
    _escritura_prohibida(monkeypatch)
    v = citas.propone_baja("zenvrax", "abc")["vale"]
    with pytest.raises(citas.NoSePuede):
        citas.confirma(v)
