# -*- coding: utf-8 -*-
"""Enviar correo: la segunda cosa de Zeno que llega a una persona.

EL CASO (2026-09-28). Era el único trabajo diario que empezaba en Zeno y terminaba fuera: Zeno
escribía la respuesta y había que abrir Gmail solo para pulsar enviar. Al abrirlo apareció algo
que conviene no olvidar: el permiso `gmail.compose`, concedido el 27-sep, YA permitía enviar
(*"Manage drafts and send emails"*). La barrera que creíamos tener no existía; lo único que
impedía enviar era que no había código.

Así que la barrera se escribe aquí, y casi todo este fichero prueba que algo NO pasa: sin PIN no
sale, hablando no sale, y un vale no manda dos veces.
"""
import sys
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
def _sesion_valida(monkeypatch):
    monkeypatch.setattr(sesion, "quien_es",
                        lambda t, ahora=None: sesion.Quien("u1", "owner", "yo@zenvrax.com"))
    yield
    sesion.limpiar_cache()


@pytest.fixture()
def _sin_diario(tmp_path, monkeypatch):
    """El diario real escribe en /datos, que aquí no existe: sin esto los renglones se perderían
    por el `except` silencioso y el test no probaría nada."""
    monkeypatch.setattr(api_mod.diario, "LIBRO", tmp_path / "hecho.jsonl")
    return api_mod.diario


# ---------------------------------------------------------------- el PIN

def test_sin_pin_no_sale_el_correo(monkeypatch):
    """LA BARRERA. Un correo enviado llega a un cliente y no se recoge: es lo mismo que publicar,
    y se trata igual. Sin esto, cualquiera con el teléfono desbloqueado escribe en tu nombre."""
    llamadas = []
    monkeypatch.setattr(api_mod.correo, "envia", lambda v: llamadas.append(v) or {"enviado": True})
    monkeypatch.setattr(api_mod.clave_mod, "pin_abierto", lambda h: False)
    r = cliente.post("/api/correo/enviar", json={"vale": "v1"}, headers=CABECERA)
    assert r.status_code == 428, r.status_code
    assert "PIN" in r.json()["detail"]
    assert llamadas == [], "ha enviado el correo sin PIN"


def test_el_428_no_echa_al_operador_fuera(monkeypatch):
    """428 y no 401 a propósito: con 401 el front borra el token y te saca de la aplicación con la
    respuesta ya escrita, que es la peor forma de perder un texto."""
    monkeypatch.setattr(api_mod.clave_mod, "pin_abierto", lambda h: False)
    assert cliente.post("/api/correo/enviar", json={"vale": "v1"},
                        headers=CABECERA).status_code != 401


def test_con_pin_si_sale(monkeypatch, _sin_diario):
    monkeypatch.setattr(api_mod.clave_mod, "pin_abierto", lambda h: True)
    monkeypatch.setattr(api_mod.correo, "envia",
                        lambda v: {"enviado": True, "para": "ana@cliente.com", "id": "d1"})
    r = cliente.post("/api/correo/enviar", json={"vale": "v1"}, headers=CABECERA)
    assert r.status_code == 200 and r.json()["enviado"] is True


# ---------------------------------------------------------------- el diario

def test_lo_enviado_queda_escrito(monkeypatch, _sin_diario):
    """Si un correo sale raro, el primer dato útil es si salió desde Zeno o desde Gmail."""
    monkeypatch.setattr(api_mod.clave_mod, "pin_abierto", lambda h: True)
    monkeypatch.setattr(api_mod.correo, "envia",
                        lambda v: {"enviado": True, "para": "ana@cliente.com", "id": "d1"})
    cliente.post("/api/correo/enviar", json={"vale": "v1"}, headers=CABECERA)
    [renglon] = _sin_diario.lee(5)
    assert renglon["op"] == "correo_enviar" and renglon["publica"] is True
    assert renglon["resultado"] == "hecho"
    assert "ana@cliente.com" in renglon["titulo"]


def test_un_envio_de_resultado_desconocido_tambien_queda_escrito(monkeypatch, _sin_diario):
    """Es EL renglón que hay que ir a mirar: el intento del que no se sabe si salió. Si no se
    apuntara, la única forma de saberlo sería recordar que pasó."""
    monkeypatch.setattr(api_mod.clave_mod, "pin_abierto", lambda h: True)

    def _revienta(v):
        raise api_mod.correo.NoSeSabe("no he podido saber si ha salido. Mira en Enviados")

    monkeypatch.setattr(api_mod.correo, "envia", _revienta)
    r = cliente.post("/api/correo/enviar", json={"vale": "v1"}, headers=CABECERA)
    assert r.status_code == 409
    [renglon] = _sin_diario.lee(5)
    assert renglon["resultado"] == "no_se_sabe", "un envío dudoso se apuntó como hecho"


def test_lo_que_ni_se_intento_no_ensucia_el_diario(monkeypatch, _sin_diario):
    """Un vale caducado no es un envío: apuntarlo llenaría el diario de cosas que no pasaron y el
    operador dejaría de mirarlo."""
    monkeypatch.setattr(api_mod.clave_mod, "pin_abierto", lambda h: True)

    def _caducado(v):
        raise api_mod.correo.NoSePuede("esa respuesta ha caducado")

    monkeypatch.setattr(api_mod.correo, "envia", _caducado)
    assert cliente.post("/api/correo/enviar", json={"vale": "v1"},
                        headers=CABECERA).status_code == 409
    assert _sin_diario.lee(5) == []


# ---------------------------------------------------------------- hablando, no

def test_no_se_puede_enviar_un_correo_hablando():
    """La regla del operador sobre la voz: solo lo reversible. Un correo no lo es.

    Se comprueba en la puerta de órdenes, que es quien empareja una frase dicha con algo de la
    pantalla: exige `reversible`, `cambia_estado` y que no cueste dinero. Enviar no cumple ni la
    primera. Si mañana alguien relajara esa condición, esto salta.
    """
    from servicio import ordenes
    assert not ordenes.se_puede_por_voz(
        {"reversible": False, "efecto": "publica", "coste_api": False}), "publicar por voz"
    assert not ordenes.se_puede_por_voz(
        {"reversible": True, "efecto": "publica", "coste_api": False}), (
        "el efecto publica pasa por voz aunque se marque reversible")


def test_la_puerta_de_ordenes_no_conoce_el_correo():
    """El otro lado de lo mismo: que no exista un atajo hablado hacia el envío. La puerta empareja
    contra lo que hay en pantalla, y el correo no entra ahí."""
    fuente = (RAIZ / "servicio" / "ordenes.py").read_text(encoding="utf-8")
    assert "correo/enviar" not in fuente and "correo.envia" not in fuente


# ---------------------------------------------------------------- la pantalla

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def test_enviar_no_es_el_boton_grande():
    """El borrador se deshace y el envío no, así que el primario sigue siendo guardar. Si enviar
    fuera el botón destacado, el dedo iría solo ahí y el escalón intermedio dejaría de existir."""
    assert 'id="bor-guarda">Guardar borrador' in WEB
    i = WEB.index('id="bor-envia"')
    # La clase va justo antes del id, en el mismo <button>.
    boton = WEB[max(0, i - 60):i + 40]
    assert 'class="b primaria" id="bor-envia"' not in boton, "enviar es el botón destacado"


def test_se_avisa_de_a_quien_va_y_de_que_no_se_recoge():
    """La confirmación lleva la dirección delante, porque el error que de verdad pasa no es
    enviar sin querer: es enviárselo a quien no era."""
    assert 'confirm("Enviar a " + p.para' in WEB
    assert "no se puede recoger" in WEB


def test_el_reintento_con_pin_no_prepara_otro_borrador():
    """Si al recibir el 428 se volviera a llamar a /api/correo/borrador, cada intento de PIN
    dejaría un borrador suelto en el Gmail del operador."""
    i = WEB.index("async function mandaConPin")
    cuerpo = WEB[i:i + 2000]
    assert "return mandaConPin(vale)" in cuerpo, "el reintento no reutiliza el mismo vale"
    assert "/api/correo/borrador" not in cuerpo, "el reintento prepara otro borrador"
