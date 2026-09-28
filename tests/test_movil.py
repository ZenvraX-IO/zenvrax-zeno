# -*- coding: utf-8 -*-
"""La aplicación se usa con el pulgar, y eso se puede romper sin que nada falle.

EL CASO (2026-09-27). El operador probó Zeno en el móvil: *"en buscar la app en móvil no está
optimizado"*. Medido sobre el código, cuatro fallos concretos:

1. El campo de búsqueda a **14px**. Con menos de 16, iOS hace ZOOM al enfocar y descoloca la
   pantalla entera. Es el fallo más visible y el más fácil de volver a meter.
2. La caja **no estaba pegada arriba**: al bajar por los resultados se perdía y había que subir del
   todo para cambiar la búsqueda.
3. Los resultados eran **texto suelto**, sin zona de toque: en un dedo, acertar en una línea de
   13px es azar.
4. **Sin botón de borrar**: vaciar un campo a base de retroceso en un teclado táctil es un castigo.

Ninguno de los cuatro lanza un error ni sale en un log. Solo se ven usándolo, y por eso van aquí.

Puros: leen el HTML, no abren un navegador.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def _html() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def _regla(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\{([^}]+)\}", css, re.S)
    assert m, f"no existe la regla {selector}"
    return m.group(1)


def test_ningun_campo_de_texto_baja_de_16px():
    """EL FALLO QUE VIO EL OPERADOR. Con menos de 16px, iOS hace zoom al enfocar el campo y la
    pantalla se descoloca. Vale para TODOS los campos, no solo el buscador: el siguiente que se
    añada tiene el mismo problema."""
    css = _html()
    for selector in (".buscador", ".campo", ".escribir input"):
        regla = _regla(css, selector)
        m = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", regla)
        assert m, f"{selector} no declara font-size: el navegador pondrá el suyo y puede ser menor"
        assert float(m.group(1)) >= 16, (
            f"{selector} tiene font-size {m.group(1)}px: iOS hará zoom al enfocarlo")


def test_la_caja_de_buscar_no_se_pierde_al_bajar():
    assert "position:sticky" in _regla(_html(), ".cajabuscar"), (
        "sin sticky hay que subir del todo para cambiar la búsqueda")


def test_cada_resultado_es_una_zona_tocable():
    """Un dedo necesita 44px. Acertar en una línea de texto de 13px es azar."""
    regla = _regla(_html(), ".doc")
    assert "min-height:44px" in regla.replace(" ", ""), "el resultado no llega a la altura mínima táctil"
    assert "padding" in regla, "sin relleno, la zona de toque es solo el texto"


def test_se_puede_borrar_la_busqueda_sin_retroceso():
    html = _html()
    assert 'id="limpiar"' in html and "limpiar\").onclick" in html, (
        "falta el botón de borrar, o está pintado pero no hace nada")


def test_el_teclado_del_movil_viene_preparado():
    """`type=search` y `enterkeyhint` cambian la tecla de Intro a Buscar; `autocapitalize` evita que
    la primera letra salga en mayúscula, que en una búsqueda no sirve de nada."""
    html = _html()
    for atributo in ('type="search"', 'enterkeyhint="search"', 'autocapitalize="off"'):
        assert atributo in html, f"al campo de buscar le falta {atributo}"


def test_la_pantalla_vacia_no_esta_vacia():
    """Una caja sola no dice qué se le puede preguntar. Las sugerencias se tocan y buscan."""
    html = _html()
    assert "EJEMPLOS" in html and "sugerencias()" in html
    assert 'closest(".sug")' in html, (
        "las sugerencias se pintan después, así que hay que atenderlas por delegación o no responden")


def test_el_fragmento_que_responde_se_ve_entero():
    """Antes el resultado era el título y un 56% pegado a 110 caracteres cortados. En el móvil hay
    sitio a lo alto: leer el fragmento es lo que evita abrir el documento para nada."""
    html = _html()
    assert "r.trozo" in html, "el front no usa el fragmento largo que ya manda la API"
    buscar = (Path(__file__).resolve().parents[3] / "cockpit" / "api" / "app" / "routers"
              / "search.py")
    if buscar.exists():
        src = buscar.read_text(encoding="utf-8")
        assert "crudo" in src and 'fila["trozo"]' in src, (
            "la API tiene que mandar el fragmento y el porcentaje por separado")


# --------------------------------------------------------------------------------------------
# QUE NO SE QUEDE COLGADO.
#
# EL CASO (2026-09-28). El operador: *"el chat se queda colgado varias veces"*. En el servidor no
# habia ni un 5xx ni una excepcion: contestaba 200 a todo. Lo que faltaba era rendirse a tiempo en
# el NAVEGADOR. `fetch` sin AbortController espera para siempre, asi que si el movil cambia de red
# o si el servicio se reinicia (un despliegue corta lo que este en curso), la peticion se queda
# muerta y la pantalla con el "pensando…" puesto, sin error y sin forma de salir de ahi.
# --------------------------------------------------------------------------------------------

def test_ninguna_peticion_puede_esperar_para_siempre():
    """EL FALLO QUE VIO EL OPERADOR. Un fetch sin tope no falla nunca: se queda."""
    h = _html()
    fn = h[h.index("async function api(ruta, opciones = {})"):]
    fn = fn[:fn.index("\nconst $ =")]
    assert "AbortController" in fn, "las peticiones no tienen tope de espera"
    assert "corta.abort()" in fn and "signal: corta.signal" in fn, (
        "se crea el abortador pero no se usa: el fetch sigue sin tope")
    assert "clearTimeout" in fn, "el reloj se queda corriendo despues de contestar"


def test_rendirse_por_tiempo_y_no_tener_red_se_dicen_distinto():
    """Son dos cosas distintas y llevan a hacer dos cosas distintas. "Failed to fetch" a secas no
    dice ninguna de las dos."""
    h = _html()
    assert "AbortError" in h
    assert "ha tardado demasiado" in h and "mira la cobertura" in h


def test_lo_que_pasa_por_un_modelo_espera_mas_que_lo_que_solo_lee():
    """Un tope unico obliga a elegir entre cortar lo lento o esperar de mas en lo rapido. El chat
    pasa por un modelo y puede tardar medio minuto; una lista, no."""
    h = _html()
    corto = int(re.search(r"const ESPERA = (\d+);", h).group(1))
    largo = int(re.search(r"const ESPERA_LARGA = (\d+);", h).group(1))
    assert largo > corto, "lo lento no espera mas que lo rapido"
    # El del chat tiene que dar margen al timeout del servidor, que es de 60 s: si el navegador se
    # rinde antes, corta una respuesta que iba a llegar.
    assert largo >= 65000, "el navegador se rinde antes que el servidor y corta respuestas buenas"
    assert '"/api/chat"' in h, "el chat no esta entre las que pueden tardar"


def test_ningun_id_se_repite_en_la_pagina():
    """EL FALLO. Al abrir las colas en una capa quedaron DOS elementos con id "confirmar-accion",
    uno en la vista de debajo y otro en la capa. `querySelector` devuelve el primero, asi que
    pulsar un boton dentro de una cola pintaba la confirmacion detras de la capa: invisible.
    Pulsar y que no pase nada visible es la peor forma de fallar en algo que publica.

    Se mira TODA la pagina y no solo ese id: el patron se repite en cuanto se duplica un bloque.
    """
    import collections
    h = _html()
    ids = re.findall(r'\bid="([a-zA-Z0-9_-]+)"', h)
    repetidos = [i for i, n in collections.Counter(ids).items() if n > 1]
    assert repetidos == [], f"ids repetidos en la pagina: {repetidos}"


def test_abrir_una_cola_esta_entre_lo_que_puede_tardar():
    """Abrir la de DMs hace que el cockpit calcule el reparto del dia entero. Con el tope corto
    se rendia a los 20 segundos y la ficha no salia NUNCA, sin dar ningun error: el catch se lo
    tragaba. Se perdio un rato buscando un fallo que el navegador ya conocia."""
    h = _html()
    lentas = re.search(r"const LENTAS = \[(.*?)\];", h, re.S).group(1)
    assert '"/api/cola"' in lentas, "abrir una cola se rinde con el tope corto"


def test_las_colas_de_hoy_se_pintan_desde_la_pantalla_que_las_enseña():
    """Estuvo puesta dentro de `busca()`, que es la funcion de buscar en la documentacion: la
    ficha no salia nunca y no habia ningun error, porque el codigo se ejecutaba en un sitio donde
    no habia nada que pintar. Un reemplazo que casa con un `catch` parecido acaba en otra
    funcion, y eso no lo dice ni el navegador ni el compilador."""
    h = _html()
    i = h.index("async function cargaPendientes()")
    fin = h.index("\n}", h.index("pintaHecho();", i))
    assert "pintaColasDeHoy();" in h[i:fin], "no se pintan desde la pantalla de Trabajo"
    # Y en ningun otro sitio: dos llamadas serian dos peticiones por carga.
    assert h.count("pintaColasDeHoy();") == 1


def test_una_fecha_no_se_enseña_en_crudo():
    """Salia "2026-09-27T19:02:30.835273+00:00" en la cabecera de cada DM. Ademas de feo obliga a
    descifrarla, y lo util no es el instante sino cuanto lleva esperando: hay respuestas de hace
    tres semanas y eso es lo que tiene que saltar a la vista."""
    h = _html()
    assert "function desdeCuando(" in h
    assert "desdeCuando(e.cuando)" in h, "la cola sigue pintando la fecha cruda"


def test_no_se_manda_al_cockpit_lo_que_tiene_boton_para_ir():
    """Decir "esto se hace en el cockpit" al lado de un boton que lleva justo al sitio donde se
    hace es lo contrario de lo que se venia a arreglar."""
    h = _html()
    assert "!pintados && !e.donde && !e.copiar" in h


def test_las_colas_de_los_dos_negocios_se_pueden_abrir():
    """Estuvo escrito a mano que las de GutLyn no se abren, que era verdad el dia que se escribio
    y dejo de serlo al montar la misma puerta en Xrise, sin que nada avisara. Ahora se mira lo
    que dice cada sistema."""
    h = _html()
    assert 'c.negocio !== "GutLyn+"' not in h, "se excluye a GutLyn a mano"
    assert "colasAbribles.xrise" in h, "no se miran las colas de GutLyn"


# --------------------------------------------------------------------------------------------
# EL FALLO (2026-09-28). El operador, mirando la cola de DMs: *"tan solo dan el link al perfil,
# pero no dice si son notas, si es un arco M1 y cual es el texto a copiar. Eso es erroneo"*.
#
# Tenia razon y era mio: salian veinte tarjetas iguales, y el texto ni se enseñaba. Sin saber QUE
# es una cosa, el mensaje de al lado no se puede pegar en ningun sitio con criterio: una nota de
# conexion y el M3 de un arco van a sitios distintos de LinkedIn.
# --------------------------------------------------------------------------------------------

def test_cada_dm_dice_que_paso_es():
    h = _html()
    assert "e.paso" in h, "la tarjeta no dice de que paso es"
    trozo = h[h.index("colaEnPantalla.forEach"):]
    trozo = trozo[:trozo.index("$(\"#cola-cuerpo\").innerHTML")]
    assert "var(--ambar)" in trozo, "el paso no destaca: hay que verlo antes que nada"


def test_el_texto_a_pegar_se_enseña_y_no_solo_se_copia():
    """En el movil hay que poder leerlo antes de pegarlo, y si el portapapeles falla (en iOS
    pasa) tiene que seguir estando a la vista."""
    h = _html()
    assert "para-pegar" in h
    assert ".para-pegar{" in h, "no tiene estilo propio: se confunde con el resto del texto"
    assert "white-space:pre-wrap" in h, "un mensaje de varias lineas sale todo seguido"


def test_se_dice_por_que_la_lista_es_la_que_es():
    """Ver solo respuestas se lee como una averia cuando lo que pasa es que el cupo del dia ya
    esta gastado. Una lista corta sin explicacion parece rota."""
    h = _html()
    assert "d.resumen" in h
    assert "ya están hechas" in h and "quedan_hoy" in h


def test_lo_que_se_pasa_del_cupo_se_ve_marcado():
    """La lista ya no se calla cuando el cupo del dia esta hecho: sale todo y lo que se pasaria
    va marcado. Sin la marca, enseñarlo SI seria una invitacion a saltarse la cuota de LinkedIn,
    que no es un numero decorativo."""
    h = _html()
    assert "e.fuera_de_cupo" in h, "no se marca lo que se pasa del cupo"
    assert "pasa del cupo de hoy" in h
