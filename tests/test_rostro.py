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


# --------------------------------------------------------------------------------------------
# La parte que se ve. Se lee del HTML: no hay forma de probar un Face ID de verdad sin un iPhone
# y una cara, pero si se puede guardar que las decisiones no se deshagan sin querer.
# --------------------------------------------------------------------------------------------

def _html() -> str:
    return (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def test_el_boton_no_se_enseña_si_no_hay_ninguna_cara_de_alta():
    """Un boton que no puede funcionar es peor que no tenerlo: se pulsa, no pasa nada, y la
    siguiente vez ya no se prueba lo que si funciona."""
    h = _html()
    assert 'id="btn-cara" class="b primaria grande" hidden' in h, "el boton nace visible"
    assert '$("#btn-cara").hidden = false' in h
    assert "if (d.hay)" in h, "nada comprueba si hay alguna cara dada de alta"


def test_cancelar_el_face_id_no_es_un_error():
    """Que el operador cancele NO es un fallo que enseñar en rojo: ha cambiado de idea, y lo que
    toca es dejarle la clave delante."""
    h = _html()
    assert '"NotAllowedError"' in h and '"AbortError"' in h


def test_la_clave_sigue_estando():
    """Un telefono se pierde y un dispositivo nuevo no tiene la llave. Si Face ID fuera la unica
    puerta, perder el movil seria perder la aplicacion."""
    h = _html()
    assert 'id="clave"' in h and 'id="btn-clave"' in h
    assert "entrarConClave" in h


def test_lo_de_activarlo_se_ofrece_una_vez_y_no_se_insiste():
    """Una aplicacion que pregunta lo mismo cada vez que la abres enseña a decir que no sin leer,
    y entonces deja de servir para avisar de nada."""
    h = _html()
    assert 'localStorage.getItem("zeno.cara.no")' in h
    assert 'localStorage.setItem("zeno.cara.no"' in h


def test_el_aviso_no_se_pone_donde_lo_van_a_borrar():
    """`#v-hoy` se repinta entero con innerHTML en cada carga. Una tarjeta metida ahi desaparece
    sola y nadie entiende por que."""
    h = _html()
    # Se corta en el cierre de la propia funcion y no mucho mas abajo: el trozo largo se comia
    # `cargaHoy`, que SI usa #v-hoy con razon, y el guardian saltaba por codigo ajeno.
    trozo = h[h.index("async function ofreceLaCara()"):]
    trozo = trozo[:trozo.index('caja.querySelector("#cara-no")')]
    assert 'querySelector("main")' in trozo, "el aviso se mete donde se repinta"
    assert '$("#v-hoy")' not in trozo


def test_el_token_se_guarda_por_el_mismo_camino_que_siempre():
    """Entrar con la cara tiene que acabar en `dentro()`, que es quien guarda la sesion. Si
    escribiera el token por su cuenta, habria dos formas de entrar y una sola vigilada."""
    h = _html()
    trozo = h[h.index("async function entrarConCara()"):]
    trozo = trozo[:trozo.index("async function darDeAltaLaCara()")]
    assert "dentro(r.token)" in trozo
    assert "guarda.poner" not in trozo, "entra por su cuenta en vez de pasar por dentro()"


def test_abrir_con_la_sesion_guardada_pasa_por_el_mismo_sitio():
    """Abrir con la sesion ya guardada es LA forma normal de abrir la aplicacion. Si ese camino
    repite a mano lo que hace `dentro()` en vez de llamarlo, todo lo que se añada a `dentro` (como
    ofrecer el Face ID) no pasa justo en el caso mas frecuente. Paso: la tarjeta no salia nunca."""
    h = _html()
    assert "if (token) dentro(token);" in h, "el arranque no pasa por dentro()"
