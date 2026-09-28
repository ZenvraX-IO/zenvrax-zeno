# -*- coding: utf-8 -*-
"""Hablar en vez de escribir, en los dos sitios donde se escribe.

EL CASO (2026-09-28). El operador: *"tanto en la busqueda como en preguntar deberia estar la
posibilidad de hacerlo via voz grabando y luego transcribiendo"*. En el movil, con una mano,
escribir una pregunta larga es justo lo que hace que no se pregunte.

Lo que estos tests guardan no es que el dictado funcione (eso se mira en un navegador), sino las
cuatro decisiones que se toman una vez y se pierden en la siguiente edicion:

1. Que este en LOS DOS campos, no solo en uno.
2. Que la voz NO salga a un tercero a transcribirse.
3. Que dictar en el chat no MANDE la pregunta solo, porque cada pregunta cuesta dinero.
4. Que se vea que el microfono esta abierto.

Puros: leen el HTML, no abren un navegador.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def _html() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def test_se_puede_dictar_en_los_dos_campos():
    """Lo pedido fue "en la busqueda Y en preguntar". Con uno solo, el otro sigue siendo teclear."""
    h = _html()
    for boton, campo in (("mic-q", "#q"), ("mic-pregunta", "#pregunta")):
        assert f'id="{boton}"' in h, f"no hay boton de dictado para {campo}"
        assert f'enchufaVoz("#{boton}", "{campo}"' in h, f"el boton {boton} no esta enganchado a {campo}"


def test_la_voz_no_sale_a_ningun_tercero():
    """EL TEST QUE IMPORTA. Se usa el reconocimiento del propio navegador. Mandar el audio a una
    API de transcripcion es un proveedor mas con el que hablas de tus clientes, y eso se decide
    aparte y no de rebote al añadir un boton."""
    h = _html()
    assert "webkitSpeechRecognition" in h, "no se usa el reconocimiento del navegador"
    # Ni MediaRecorder (grabar para mandar) ni ningun destino de audio conocido.
    for prohibido in ("MediaRecorder", "getUserMedia", "openai.com", "deepgram", "assemblyai",
                      "speech.googleapis", "whisper"):
        assert prohibido not in h, f"la voz acaba en {prohibido}: eso graba y manda audio fuera"


def test_dictar_en_el_chat_no_manda_la_pregunta():
    """Cada pregunta cuesta dinero y una transcripcion puede salir torcida. Lo ultimo que quieres
    es pagar por una frase que no dijiste."""
    h = _html()
    m = re.search(r'enchufaVoz\("#mic-pregunta",\s*"#pregunta",\s*"[^"]+",\s*([^)]*)\)', h)
    assert m, "no se encuentra el enganche del chat"
    assert m.group(1).strip() == "null", (
        "el dictado del chat lleva una accion al terminar: si esa accion pregunta, gasta sola")
    # En buscar SI se lanza la busqueda: buscar no cuesta nada. Se busca en la LINEA entera y no
    # con [^)]*: la propia llamada lleva parentesis dentro y el corte se quedaba a medias.
    linea = [x for x in h.splitlines() if 'enchufaVoz("#mic-q"' in x]
    assert linea and "busca()" in linea[0], "dictar en buscar no lanza la busqueda"


def test_se_ve_que_el_microfono_esta_abierto():
    """Un microfono abierto sin señal visible es la clase de cosa que se queda encendida sin que
    nadie lo sepa."""
    h = _html()
    assert ".micro.oyendo{" in h, "no hay estado visible de escucha"
    regla = re.search(r"\.micro\.oyendo\{([^}]+)\}", h).group(1)
    assert "var(--ambar)" in regla, "el estado de escucha no cambia de color"
    assert 'classList.add("oyendo")' in h and 'classList.remove("oyendo")' in h, (
        "la señal se enciende o no se apaga")


def test_el_boton_no_se_enseña_si_el_navegador_no_sabe_escuchar():
    """Firefox no lo tiene. Un boton que no puede funcionar es peor que no tenerlo."""
    h = _html()
    assert 'id="mic-q" class="micro" hidden' in h and 'id="mic-pregunta" class="micro" hidden' in h, (
        "el boton nace visible: se vera un instante en los navegadores que no pueden")
    assert "b.hidden = !Voz.hay" in h, "nada decide si el boton se enseña"


def test_el_boton_de_dictar_es_de_dedo():
    """44px es el minimo tocable. Mas pequeño se falla y se acaba escribiendo igual, que es lo que
    se venia a evitar."""
    regla = re.search(r"\.micro\{([^}]+)\}", _html()).group(1)
    for medida in ("width:44px", "height:44px"):
        assert medida in regla.replace(" ", ""), f"el boton de dictar no cumple {medida}"


def test_el_fallo_del_microfono_se_dice_en_castellano():
    """"not-allowed" en pantalla no dice que hacer. Y callarse y fallar no pueden verse igual."""
    h = _html()
    for caso in ("not-allowed", "no-speech", "audio-capture"):
        assert f'"{caso}"' in h, f"el error {caso} no se traduce"
    assert "no has dado permiso al micrófono" in h


def test_lo_dictado_se_añade_y_no_pisa_lo_escrito():
    """Puedes escribir media frase y dictar el resto. Pisar el campo borraria lo tecleado sin
    avisar, que es de las cosas que no se perdonan en un movil."""
    assert "campo.value.trim() + \" \"" in _html(), "lo dictado sustituye en vez de añadirse"
