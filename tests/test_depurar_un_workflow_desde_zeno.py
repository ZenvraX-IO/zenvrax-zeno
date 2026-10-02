# -*- coding: utf-8 -*-
"""Por qué falla un workflow, sin abrir una consola.

EL CASO (2026-10-02). Zeno avisaba de que `A13d` fallaba y el aviso decía esto y nada más:

    🚨 Error en workflow: A13d LinkedIn DM Metrics Weekly

Para saber qué pasaba hubo que entrar en la base de n8n, sacar la última ejecución, desenredar el
árbol aplanado que guarda n8n y leer el nodo que reventó. El operador, al verlo: *"cuando falle un
workflow, pon en Zeno un botón que diga depurar para poder ver de qué viene y poderlo solucionar.
Si no, estaremos siempre con la consola de Claude Code y no es la situación"*.

LO QUE RESUELVE, que no es arreglar el workflow: saber por dónde empezar. El diagnóstico dice qué
nodo revienta, con qué mensaje, y **si esto falla siempre o fue una vez**, que es lo que de verdad
decide si hay que correr. A13d llevaba cinco semanas fallando todas las semanas.
"""
import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
API = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")
LECTOR = (RAIZ / "lector.py").read_text(encoding="utf-8")


def _funcion(fuente: str, nombre: str) -> str:
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nombre:
            return ast.unparse(n)
    raise AssertionError(f"no existe {nombre}")


# ------------------------------------------------------------------ 1. el aviso trae el nombre

def test_un_aviso_de_workflow_roto_se_puede_depurar():
    """Sin el nombre del workflow, la pantalla no tiene a quién preguntar y el botón no puede
    existir. Es la pieza que faltaba."""
    cuerpo = _funcion(LECTOR, "_aviso_suelto")
    # SE EXIGE LA ASIGNACION, no que aparezca la palabra: el primer intento de este test pasaba
    # aunque se quitara la linea, porque "workflow" sale en mas sitios de la funcion.
    assert "aviso['workflow'] =" in cuerpo, "el aviso ya no guarda a que workflow se refiere"
    assert "alert:" in cuerpo, "no reconoce los avisos de workflow roto"


def test_los_avisos_normales_NO_llevan_boton():
    """Un botón Depurar en una tarea o en un aviso de negocio sería ruido: no hay nada que
    depurar."""
    i = WEB.index("a.workflow ?")
    assert "data-depurar" in WEB[i:i + 200]
    # El botón cuelga de que el aviso traiga `workflow`, no de que exista la tarjeta.
    assert "(a.workflow ?" in WEB


# ------------------------------------------------------------------ 2. dice lo que importa

def test_el_diagnostico_dice_si_falla_SIEMPRE_o_fue_una_vez():
    """LO QUE DECIDE SI HAY QUE CORRER. Un mensaje de error sin esto no distingue un tropiezo de
    algo que lleva cinco semanas roto, que era justo el caso de A13d."""
    ops = (RAIZ.parent / "zenvrax-io" / "cockpit" / "api" / "app" / "routers" / "ops.py")
    if not ops.exists():
        return                                    # el cockpit vive en otro repo; se mira si está
    cuerpo = _funcion(ops.read_text(encoding="utf-8"), "workflow_diagnostico")
    assert "veredicto" in cuerpo
    assert "falla SIEMPRE" in cuerpo


def test_el_detalle_sale_de_la_ultima_FALLIDA():
    """Si se mirara la última a secas, un workflow arreglado hace diez minutos enseñaría el éxito
    de después y no el fallo que se quiere entender."""
    ops = (RAIZ.parent / "zenvrax-io" / "cockpit" / "api" / "app" / "routers" / "ops.py")
    if not ops.exists():
        return
    cuerpo = _funcion(ops.read_text(encoding="utf-8"), "workflow_diagnostico")
    assert "next((f for f in filas if f['status'] != 'success'), None)" in cuerpo


def test_la_pantalla_enseña_el_VEREDICTO_primero():
    """El mensaje de error es el detalle; lo que decide es cuánto lleva roto."""
    cuerpo = WEB[WEB.index("async function depura("):]
    cuerpo = cuerpo[:cuerpo.index("async function preguntar")]
    assert "d.veredicto" in cuerpo
    assert cuerpo.index("d.veredicto") < cuerpo.index("det.mensaje")


def test_la_pantalla_enseña_el_NODO_que_revienta():
    """Sin el nodo, el mensaje de error no dice dónde mirar."""
    cuerpo = WEB[WEB.index("async function depura("):WEB.index("async function preguntar")]
    assert "det.nodo" in cuerpo


# ------------------------------------------------------------------ 3. no toca nada

def test_depurar_SOLO_LEE():
    """No arregla el workflow ni lo relanza. Si pudiera, haría falta PIN y confirmación, y esto
    tiene que poder pulsarse sin pensarlo."""
    cuerpo = WEB[WEB.index("async function depura("):WEB.index("async function preguntar")]
    assert "method:" not in cuerpo, "hace una peticion que no es GET: estaria tocando algo"
    assert "abreElPin" not in cuerpo
    cuerpo_api = _funcion(API, "workflow_depurar")
    assert "ejecutor" not in cuerpo_api, "el endpoint de depurar puede ejecutar acciones"


def test_si_el_cockpit_no_contesta_se_DICE():
    """Un botón que se queda en 'mirando…' para siempre es peor que no tenerlo."""
    cuerpo = WEB[WEB.index("async function depura("):WEB.index("async function preguntar")]
    assert "catch" in cuerpo and "aviso-fallo" in cuerpo
    # SE ACOTA AL BLOQUE `catch`, hasta su `return`: cortando por los primeros 200 caracteres se
    # colaba el `boton.disabled = false` del camino BUENO, que viene justo despues, y el test
    # pasaba aunque el catch dejara el boton bloqueado.
    bloque = cuerpo.split("catch")[1]
    bloque = bloque[:bloque.index("return")]
    assert "boton.disabled = false" in bloque, (
        "si el cockpit no contesta, el boton se queda en 'mirando...' para siempre")
    cuerpo_api = _funcion(API, "workflow_depurar")
    assert "502" in cuerpo_api or "503" in cuerpo_api
