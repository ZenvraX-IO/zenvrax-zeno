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
