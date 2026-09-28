# -*- coding: utf-8 -*-
"""Entrar con Face ID: que valga, y sobre todo que no valga nada que no sea el.

EL CASO (2026-09-28). El operador pidio entrar con Face ID y no escribir la clave cada vez. Esto
abre una puerta NUEVA a la aplicacion, y una puerta nueva es donde se miran las cosas dos veces.

La tentacion facil era "Face ID para desbloquear un token guardado": se monta en media hora y no
demuestra nada, porque quien copie el almacenamiento del navegador entra igual. Aqui la firma se
comprueba en el servidor, y estos tests son los que impiden que eso se relaje luego.

Puros: ni red, ni navegador, ni un telefono.
"""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

pytest.importorskip("webauthn", reason="hace falta la libreria de passkeys")

from servicio import rostro  # noqa: E402


@pytest.fixture(autouse=True)
def _fichero_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(rostro, "FICHERO", tmp_path / "rostros.json")
    rostro._RETOS.clear()
    yield


def _con_una_cara(monkeypatch, **campos):
    rostro._guarda({"caras": [{"id": "AAAA", "clave": "BBBB", "contador": 3,
                               "apodo": "el iPhone", "cuando": 0, **campos}]})


# ---------------------------------------------------------------- lo que no puede pasar

def test_un_reto_vale_una_sola_vez():
    """EL TEST QUE IMPORTA. Sin esto, quien grabara una respuesta buena podria repetirla tal cual
    y entrar sin tener ni el telefono ni la cara."""
    crudo = rostro._reto()
    from webauthn.helpers import bytes_to_base64url
    b64 = bytes_to_base64url(crudo)
    rostro._quema(b64)
    with pytest.raises(rostro.NoVale):
        rostro._quema(b64)


def test_un_reto_caduca():
    import time
    from webauthn.helpers import bytes_to_base64url
    b64 = bytes_to_base64url(rostro._reto())
    rostro._RETOS[b64] = time.time() - rostro.VIVE_RETO - 1
    with pytest.raises(rostro.NoVale):
        rostro._quema(b64)


def test_un_reto_inventado_no_cuela():
    with pytest.raises(rostro.NoVale):
        rostro._quema("esto-no-lo-ha-dado-nadie")


def test_sin_ninguna_cara_dada_de_alta_no_se_puede_entrar():
    """Que no haya ninguna NO puede leerse como "pasa cualquiera", que es la forma clasica de
    dejar una puerta abierta sin querer."""
    assert not rostro.hay()
    with pytest.raises(rostro.NoVale):
        rostro.entrada_empieza()


def test_un_telefono_que_no_esta_de_alta_no_entra(monkeypatch):
    _con_una_cara(monkeypatch)
    import base64
    from webauthn.helpers import bytes_to_base64url
    b64 = bytes_to_base64url(rostro._reto())
    cliente = base64.urlsafe_b64encode(
        json.dumps({"challenge": b64}).encode()).decode().rstrip("=")
    with pytest.raises(rostro.NoVale, match="no está dado de alta"):
        rostro.entrada_termina({"id": "OTRO", "response": {"clientDataJSON": cliente}})


def test_una_respuesta_sin_datos_no_pasa():
    for basura in ({}, {"response": {}}, {"id": "AAAA"}, {"id": "AAAA", "response": {}}):
        with pytest.raises(rostro.NoVale):
            rostro.entrada_termina(basura)


def test_la_firma_se_comprueba_de_verdad():
    """Que el modulo llame a la libreria de verificacion, y con verificacion de usuario obligada.

    Se lee del codigo porque es una decision que se puede deshacer en una linea: quitar
    `require_user_verification` deja pasar un telefono solo desbloqueado, y entonces esto ya no es
    Face ID, es "tener el movil".
    """
    fuente = (RAIZ / "servicio" / "rostro.py").read_text(encoding="utf-8")
    assert "verify_authentication_response" in fuente
    assert "verify_registration_response" in fuente
    assert fuente.count("require_user_verification=True") == 2, (
        "falta exigir que el teléfono compruebe quién eres en alguno de los dos caminos")
    assert "UserVerificationRequirement.REQUIRED" in fuente
    assert "expected_origin=ORIGEN" in fuente, "sin origen esperado, vale una firma de otra web"
    assert "expected_rp_id=DOMINIO" in fuente


def test_el_dominio_no_lleva_esquema():
    """`rp_id` es el DOMINIO. Con "https://..." delante el navegador rechaza el alta y no dice por
    que: se queda en un error generico que cuesta media tarde."""
    assert "://" not in rostro.DOMINIO
    assert rostro.ORIGEN.startswith("https://")
    assert rostro.ORIGEN.endswith(rostro.DOMINIO)


def test_un_contador_que_va_hacia_atras_se_denuncia(monkeypatch):
    """Un contador que baja significa que hay una copia de la llave por ahi. Eso se avisa, no se
    ignora."""
    _con_una_cara(monkeypatch, contador=10)

    class Falsa:
        new_sign_count = 5

    monkeypatch.setattr(rostro.webauthn, "verify_authentication_response", lambda **k: Falsa())
    import base64
    from webauthn.helpers import bytes_to_base64url
    b64 = bytes_to_base64url(rostro._reto())
    cliente = base64.urlsafe_b64encode(
        json.dumps({"challenge": b64}).encode()).decode().rstrip("=")
    with pytest.raises(rostro.NoVale, match="contador viejo"):
        rostro.entrada_termina({"id": "AAAA", "response": {"clientDataJSON": cliente}})


def test_el_contador_a_cero_de_apple_no_bloquea(monkeypatch):
    """Las passkeys del llavero de Apple mandan el contador a cero SIEMPRE. Si eso se tratara como
    un contador que retrocede, el Face ID del iPhone no funcionaria nunca, que es justo el
    telefono para el que se ha hecho esto."""
    _con_una_cara(monkeypatch, contador=10)

    class Falsa:
        new_sign_count = 0

    monkeypatch.setattr(rostro.webauthn, "verify_authentication_response", lambda **k: Falsa())
    import base64
    from webauthn.helpers import bytes_to_base64url
    b64 = bytes_to_base64url(rostro._reto())
    cliente = base64.urlsafe_b64encode(
        json.dumps({"challenge": b64}).encode()).decode().rstrip("=")
    assert rostro.entrada_termina({"id": "AAAA", "response": {"clientDataJSON": cliente}})["vale"]


# ---------------------------------------------------------------- lo que si tiene que poder

def test_se_puede_dar_de_baja_un_telefono(monkeypatch):
    """Una credencial que se da de alta y no de baja es una llave que no se puede cambiar. Si se
    pierde el movil, esto es lo unico que cierra la puerta."""
    _con_una_cara(monkeypatch)
    assert rostro.cuantas() == 1
    assert rostro.olvidar("AAAA") == 0
    assert not rostro.hay()


def test_dar_de_baja_uno_no_echa_a_los_demas(monkeypatch):
    rostro._guarda({"caras": [{"id": "A", "clave": "x", "contador": 0, "apodo": "iPhone"},
                              {"id": "B", "clave": "y", "contador": 0, "apodo": "iPad"}]})
    assert rostro.olvidar("A") == 1
    assert [c["id"] for c in rostro._lee()["caras"]] == ["B"]


def test_el_alta_pide_que_la_llave_se_quede_en_el_telefono():
    """`resident_key` REQUIRED es lo que hace que el llavero la guarde y sobreviva a que iOS
    limpie el almacenamiento del sitio, que es EL PROBLEMA que se venia a resolver."""
    fuente = (RAIZ / "servicio" / "rostro.py").read_text(encoding="utf-8")
    assert "ResidentKeyRequirement.REQUIRED" in fuente


def test_el_fichero_roto_no_tumba_la_aplicacion(monkeypatch):
    rostro.FICHERO.parent.mkdir(parents=True, exist_ok=True)
    rostro.FICHERO.write_text("{esto no es json", encoding="utf-8")
    assert rostro._lee() == {"caras": []}
    assert not rostro.hay()


def test_este_modulo_no_emite_sesiones():
    """Emitir sesiones es de clave.py, que es donde estan la duracion y la firma. Dos sitios que
    emiten sesiones son dos sitios que caducan distinto, y el segundo se olvida al cambiar el
    primero."""
    fuente = (RAIZ / "servicio" / "rostro.py").read_text(encoding="utf-8")
    for prohibido in ("def emite", "hmac.new", "jwt", "z1."):
        assert prohibido not in fuente, f"rostro.py está emitiendo sesiones por su cuenta: {prohibido}"
