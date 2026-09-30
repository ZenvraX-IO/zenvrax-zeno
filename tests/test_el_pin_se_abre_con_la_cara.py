# -*- coding: utf-8 -*-
"""Aprobar sin teclear el PIN: se abre con Face ID.

EL CASO (2026-09-30). El operador pidió el PIN porque no lo recordaba, se le puso uno nuevo, y
dijo: *"sigo necesitándolo para aprobar"*.

Lo necesitaba porque los TRES sitios que lo piden saltaban directos al teclado, teniendo el camino
de la cara construido y probado EN EL SERVIDOR desde que se montó Face ID. `POST /api/rostro/pin`
existía, con sus tests, y la pantalla no lo llamaba nunca: el dato estaba y no tenía botón.

NO REBAJA LA BARRERA, y por eso vale: el PIN son cifras que se escriben en la calle y se miran por
encima del hombro; esto es biometría comprobada por el chip del teléfono. Se exige lo mismo,
demostrar otra vez que eres tú antes de lo que no se deshace.
"""
import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
API = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")


def test_los_tres_sitios_prueban_la_cara_antes_del_teclado():
    """LA BARRERA. Si alguno volviera a saltar directo al `prompt`, ese camino seguiría pidiendo
    teclear el PIN y nadie lo notaría: los otros dos funcionarían."""
    assert 'prompt("PIN' not in WEB, "hay un sitio que pide el PIN sin ofrecer la cara"
    assert WEB.count("abreElPin(") >= 4, "faltan sitios por pasar por abreElPin (3 usos + la def)"


def test_la_pieza_llama_al_endpoint_que_ya_existia():
    """Y no a uno nuevo: `/api/rostro/pin` estaba escrito, probado y desplegado."""
    i = WEB.index("async function abreElPin")
    cuerpo = WEB[i:i + 1600]
    assert '"/api/rostro/pin"' in cuerpo
    assert '"/api/rostro/entrar"' in cuerpo, "sin el reto no hay nada que firmar"


def test_si_se_cancela_la_cara_queda_el_teclado():
    """Cancelar el Face ID no es un fallo, es cambiar de idea. Si ahí se acabara el camino, el
    operador se quedaría sin poder aprobar hasta recargar."""
    i = WEB.index("async function abreElPin")
    cuerpo = WEB[i:i + 1600]
    assert "catch" in cuerpo and "prompt(para)" in cuerpo
    # Y el teclado va DESPUÉS del intento con la cara, no dentro de su `try`.
    assert cuerpo.index("catch") < cuerpo.index("prompt(para)")


def test_sin_face_id_en_el_aparato_tampoco_se_bloquea():
    """En un portátil sin biometría, `hayCara` es falso: tiene que ir al teclado sin intentar
    nada, no fallar."""
    i = WEB.index("async function abreElPin")
    cuerpo = WEB[i:i + 1600]
    assert "if (hayCara)" in cuerpo


def test_una_cara_que_no_vale_no_abre_la_ventana():
    """Lo que no puede pasar: que un fallo de firma se lea como éxito y la ventana quede abierta.
    Solo se devuelve `true` después de que el servidor acepte."""
    i = WEB.index("async function abreElPin")
    cuerpo = WEB[i:i + 1600]
    j = cuerpo.index('"/api/rostro/pin"')
    assert "return true" in cuerpo[j:j + 260], "devuelve true sin esperar a que el servidor acepte"
    # Y CON `await`. Sin el, la peticion sale y el `return true` no espera respuesta: una firma
    # rechazada se leeria como ventana abierta, y el siguiente intento de publicar daria 428 sin
    # que nadie entienda por que.
    assert 'await api("/api/rostro/pin"' in cuerpo, "la llamada no se espera: falta el await"


def test_el_endpoint_del_servidor_sigue_exigiendo_la_firma():
    """El otro lado de lo mismo: si `/api/rostro/pin` dejara de comprobar la firma, la ventana se
    abriría con cualquier cosa que se le mande."""
    arbol = ast.parse(API)
    for n in ast.walk(arbol):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "rostro_abre_pin":
            cuerpo = ast.unparse(n)
            assert "entrada_termina" in cuerpo, "no comprueba la firma del Face ID"
            assert "NoVale" in cuerpo and "401" in cuerpo, "una firma mala no se rechaza"
            assert "abre_con_rostro" in cuerpo
            return
    raise AssertionError("no existe rostro_abre_pin")


def test_la_ventana_que_abre_es_la_MISMA_que_la_del_pin():
    """Si abriera una ventana distinta o más larga, la cara estaría dando más permiso que el PIN y
    dejaría de ser 'lo mismo por otra puerta'."""
    from servicio import clave

    # SE EJECUTAN Y SE COMPARA, en vez de buscar el nombre de una constante: la primera versión de
    # este test adivinó que se llamaba `PIN_GRACIA` y se llama `GRACIA`. Adivinar un nombre no
    # comprueba nada; medir lo que hace, sí.
    ahora = 1_000_000.0
    con_cara = clave.abre_con_rostro("sesion-a", ahora=ahora)
    assert con_cara == ahora + clave.GRACIA, (
        f"la cara abre {con_cara - ahora}s y el PIN {clave.GRACIA}s: no es la misma ventana")
    # Y que de verdad quede abierta, no solo que devuelva un número.
    assert clave.pin_abierto("sesion-a", ahora=ahora + 1)
    assert not clave.pin_abierto("otra-sesion", ahora=ahora + 1), (
        "abrir la ventana de una sesión la abre para todas")
