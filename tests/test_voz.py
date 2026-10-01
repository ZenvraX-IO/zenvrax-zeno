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
    for boton in ("mic-q", "mic-pregunta"):
        assert f'id="{boton}"' in h, f"no hay boton de dictado {boton}"
    # Buscar dicta al campo; el del chat abre una conversacion entera, que es otra cosa.
    assert 'enchufaVoz("#mic-q", "#q"' in h, "el boton de buscar no esta enganchado al campo"
    assert '$("#mic-pregunta").onclick = conversa' in h, "el boton del chat no abre la conversacion"


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


def test_lo_dicho_va_primero_a_la_puerta_que_no_cuesta():
    """CAMBIO DE DECISION, 28-sep. Por la mañana el dictado del chat dejaba la frase escrita y no
    la mandaba, porque cada pregunta cuesta. Por la tarde el operador pidio conversacion por voz,
    y una conversacion que no contesta no es una conversacion.

    La proteccion del gasto no se quita, se mueve: lo dicho va PRIMERO a /api/orden, que empareja
    con reglas y cuesta cero. Solo si no era una orden se manda al chat, que si gasta. Cerrar una
    tarea hablando sale gratis.
    """
    h = _html()
    conversa = h[h.index("async function conversa()"):]
    conversa = conversa[:conversa.index("if (Voz.hay)")]
    assert conversa.index("/api/orden") < conversa.index("preguntar("), (
        "se pregunta (y se paga) antes de mirar si era una orden")
    # En buscar SI se lanza la busqueda: buscar no cuesta nada.
    linea = [x for x in h.splitlines() if 'enchufaVoz("#mic-q"' in x]
    assert linea and "busca()" in linea[0], "dictar en buscar no lanza la busqueda"


def test_quien_decide_que_es_un_si_es_el_servidor():
    """La regla de que cuenta como un si vive en `ordenes.py`, con sus tests. Repetirla en
    JavaScript serian dos reglas que se separan a la primera, y la copia del navegador es la que
    decide si se ejecuta."""
    h = _html()
    conversa = h[h.index("async function conversa()"):]
    conversa = conversa[:conversa.index("if (Voz.hay)")]
    assert 'vale: o.vale' in conversa, "la respuesta no se manda al servidor a interpretar"
    assert 'q.estado === "si"' in conversa
    for suelto in ('=== "si "', '.includes("si")', 'toLowerCase() === "si"'):
        assert suelto not in h, f"el navegador interpreta el si por su cuenta: {suelto}"


def test_ejecutar_sigue_pasando_por_la_unica_puerta():
    """La voz no abre un camino nuevo para ejecutar: usa /api/accion/confirmar, el mismo vale de
    un solo uso y el mismo diario. Si la voz tuviera su propia salida, habria dos sitios por los
    que sale algo al mundo y solo uno estaria vigilado."""
    h = _html()
    conversa = h[h.index("async function conversa()"):]
    conversa = conversa[:conversa.index("if (Voz.hay)")]
    assert "/api/accion/confirmar" in conversa


def test_zeno_solo_habla_si_le_has_hablado():
    """Lo eligio el operador: si escribes, contesta escrito. Hablar solo porque si es lo que hace
    que uno lo cierre en la primera reunion."""
    h = _html()
    # `preguntar` es lo que usa el chat escrito, y no puede decir nada en alto por su cuenta.
    escrito = h[h.index("async function preguntar(desde, yaPintada)"):]
    escrito = escrito[:escrito.index("function cargaChat()")]
    assert "Habla.di" not in escrito, "el chat escrito contesta en voz alta"
    # Y la conversacion, que empieza por voz, si.
    conversa = h[h.index("async function conversa()"):]
    assert "Habla.di" in conversa


def test_hablar_no_puede_colgar_la_conversacion():
    """`onend` no siempre llega (iOS al bloquear la pantalla, textos largos). Sin red de
    seguridad, la conversacion se queda esperando para siempre a algo que ya termino."""
    h = _html()
    di = h[h.index("    di(texto) {"):]
    di = di[:di.index("  };")]
    assert "setTimeout(fin" in di, "si onend no llega, la conversacion se queda colgada"
    assert "u.onerror" in di


def test_se_ve_que_el_microfono_esta_abierto():
    """Un microfono abierto sin señal visible es la clase de cosa que se queda encendida sin que
    nadie lo sepa."""
    h = _html()
    assert ".micro.oyendo{" in h, "no hay estado visible de escucha"
    regla = re.search(r"\.micro\.oyendo\{([^}]+)\}", h).group(1)
    assert "var(--ambar)" in regla, "el estado de escucha no cambia de color"
    assert 'classList.add("oyendo")' in h and 'classList.remove("oyendo")' in h, (
        "la señal se enciende o no se apaga")


def test_el_boton_que_escucha_no_se_mueve():
    """Latia con transform:scale, o sea el objetivo del dedo crecia y encogia mientras intentas
    volver a pulsarlo para parar. El navegador de prueba no consiguio pulsarlo en 30 segundos. El
    halo puede latir; la caja del boton, no."""
    regla = re.search(r"@keyframes late\{([^@]+?)\}\s", _html(), re.S).group(1)
    assert "transform" not in regla, "la animacion mueve el boton: el dedo persigue un blanco movil"
    assert "box-shadow" in regla


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


# --------------------------------------------------------------------------------------------
# Las colas de trabajo diario: ir, copiar y marcar.
#
# EL CASO (2026-09-28). El operador: que los DMs del dia salgan en Zeno "para poderlos marcar
# desde esa aplicacion y no ir al cockpit". El trabajo se hace EN LinkedIn o EN X, asi que hacen
# falta las tres cosas: el enlace al sitio, el texto, y el boton de anotarlo.
# --------------------------------------------------------------------------------------------

def test_una_cola_de_trabajo_lleva_ir_copiar_y_marcar():
    h = _html()
    trozo = h[h.index("async function abreCola("):]
    trozo = trozo[:trozo.index("async function conversa()")]
    assert "Ir y responder" in trozo, "no hay enlace al sitio donde se hace el trabajo"
    assert "data-copiar=" in trozo, "no se puede copiar el texto"
    assert "data-cola-accion=" in trozo, "no se puede marcar"
    assert trozo.index("Ir y responder") < trozo.index("data-copiar"), (
        "copiar sale antes que ir: no es el orden en que se hace")


def test_si_el_portapapeles_falla_el_texto_no_se_pierde():
    """En iOS el portapapeles falla si no lo pide un gesto, y a veces falla igual. Dejar al
    operador sin el texto y con un boton que no hizo nada es peor que no tener boton."""
    h = _html()
    trozo = h[h.index('querySelectorAll("[data-copiar]")'):]
    trozo = trozo[:trozo.index("[data-cola-accion]")]
    assert "catch" in trozo and "textarea" in trozo, (
        "si copiar falla, el texto no se enseña en ningún sitio")


# ------------------------------------------------------------------ lo dictado sale UNA vez
#
# EL CASO (2026-10-01). El operador, con una captura del chat donde cada frase suya aparecia dos
# veces y Zeno contestaba una: *"en el chat de Zeno duplica las notas por voz"*.
#
# `conversa()` pinta lo oido nada mas oirlo, porque lo necesita para las ordenes. Y despues
# llamaba a `preguntar()`, que pintaba OTRA burbuja con lo mismo. Escribiendo nunca pasaba, y por
# eso llevaba tiempo sin verse.
#
# Y NO ERA SOLO LO QUE SE VE: `preguntar()` lee los turnos de la PANTALLA para mandarlos como
# contexto, asi que la frase repetida tambien le llegaba al modelo.

def test_lo_dictado_no_se_pinta_dos_veces():
    h = _html()
    conversa = h[h.index("async function conversa()"):h.index("if (Voz.hay)")]
    assert "preguntar(oido.texto, true)" in conversa, (
        "el modo voz vuelve a pintar lo que ya habia pintado: sale dos veces")


def test_preguntar_respeta_que_ya_este_pintada():
    h = _html()
    escrito = h[h.index("async function preguntar(desde, yaPintada)"):h.index("function cargaChat()")]
    assert "if (yaPintada) turnos.pop();" in escrito, (
        "la frase repetida sigue viajando al modelo como contexto")
    assert "else burbuja(\"tu\", texto);" in escrito


def test_escribiendo_SI_se_pinta(monkeypatch=None):
    """Lo que no puede pasar al arreglarlo: que el chat escrito deje de pintar lo que escribes.
    Sin `yaPintada` tiene que seguir pintando."""
    h = _html()
    escrito = h[h.index("async function preguntar(desde, yaPintada)"):h.index("function cargaChat()")]
    i = escrito.index("if (yaPintada)")
    assert "burbuja(\"tu\", texto)" in escrito[i:i + 120], (
        "sin la rama `else` el chat escrito no pinta nada")


# ------------------------------------------------------------------ el microfono lo cierras TU
#
# EL CASO (2026-10-01). El operador: *"cuando le doy al micro para poder hablar, deberia ser algo
# que le diera y luego cuando termina de hablar tambien le diera para finalizar. Ahora depende de
# lo que son los silencios que hay entre medio"*.
#
# Estaba en `continuous = false`: una frase y para. Bien para un "si", inservible para dictar una
# idea, que es justo cuando uno hace pausas para pensar.

def _arranca() -> str:
    h = _html()
    return h[h.index("arranca(alOir, alAcabar, largo)"):h.index("// Engancha un boton de microfono")]


def test_dictar_usa_el_modo_que_no_cierra_solo():
    h = _html()
    conversa = h[h.index("async function conversa()"):h.index("if (Voz.hay)")]
    assert "await oye(dice, true)" in conversa, "dictar vuelve a cortarse en la primera pausa"


def test_un_si_o_un_no_SIGUEN_cortandose_solos():
    """Lo que no hay que hacer al arreglarlo: obligar a pulsar dos veces para decir 'si'. La
    confirmacion son dos palabras y el corte automatico ahi esta bien."""
    h = _html()
    conversa = h[h.index("async function conversa()"):h.index("if (Voz.hay)")]
    # La segunda escucha, la de la confirmacion, no pide modo largo.
    i = conversa.index("const r = await oye(dice")
    assert "oye(dice)" in conversa[i:i + 40], (
        "la confirmacion tambien pide pulsar para terminar: para decir 'si' sobra")


def test_una_pausa_NO_es_un_error():
    """`no-speech` es lo que manda el navegador cuando te callas un momento. Tratarlo como fallo
    cerraria el microfono por exactamente lo que el operador pidio que no lo cerrara."""
    cuerpo = _arranca()
    assert 'if (largo && e.error === "no-speech") return;' in cuerpo


def test_si_el_navegador_cierra_solo_se_vuelve_a_abrir():
    """Safari, que es el navegador del iPhone donde se usa esto, cierra a los pocos segundos de
    silencio aunque `continuous` este puesto, y lo hace por `onend` sin dar error."""
    cuerpo = _arranca()
    i = cuerpo.index("r.onend")
    trozo = cuerpo[i:i + 420]
    assert "abre()" in trozo, "sin reabrir, en el movil sigue cortandose en cada pausa"
    assert "!pediste" in trozo, "reabriria incluso cuando lo has cerrado tu"


def test_al_pulsar_parar_NO_se_vuelve_a_abrir():
    """EL FALLO QUE TUVE QUE ARREGLAR ANTES DE APLICARLO: con una sola bandera, pulsar parar
    disparaba `onend` y el microfono se reabria solo. Son dos cosas distintas: que lo hayas pedido
    y que ya se haya entregado el texto."""
    cuerpo = _arranca()
    assert "pediste = true" in cuerpo and "entregado = true" in cuerpo
    i = cuerpo.index("viva = { stop:")
    assert "pediste = true" in cuerpo[i:i + 140], (
        "parar no marca la bandera antes de cerrar: el onend reabriria")


def test_el_texto_se_entrega_UNA_sola_vez():
    """Con reaperturas hay varios `onend`, y sin esto `alAcabar` se llamaria una vez por cada uno:
    la misma frase enviada varias veces."""
    cuerpo = _arranca()
    assert "if (entregado) return;" in cuerpo


def test_lo_dicho_se_acumula_entre_pausas():
    """Si cada reapertura empezara de cero, dictar una frase larga devolveria solo el ultimo
    trozo, que es peor que el fallo original."""
    cuerpo = _arranca()
    assert "dicho +=" in cuerpo
    assert 'dicho && !dicho.endsWith(" ")' in cuerpo, "las tandas se pegarian sin espacio"


def test_SIGUE_habiendo_un_tope():
    """La razon por la que esto estaba corto sigue siendo buena: un microfono abierto se olvida
    abierto. A los tres minutos se cierra y se entrega lo que haya."""
    cuerpo = _arranca()
    assert "3 * 60 * 1000" in cuerpo and "setTimeout" in cuerpo
    assert "clearTimeout(reloj)" in cuerpo, "el reloj queda vivo tras entregar"


def test_la_pantalla_dice_que_hay_que_pulsar():
    """Un microfono que no se cierra solo y no lo dice se queda abierto sin que nadie lo sepa."""
    h = _html()
    assert "pulsa para terminar" in h
