# -*- coding: utf-8 -*-
"""Abrir Zeno no hace esperar: nada se pide en fila que pueda ir a la vez, y el adorno no bloquea.

EL CASO (2026-09-30). El operador: *"¿se puede de alguna manera rebajar la latencia y que en el
momento de la carga no tarde tantos segundos?"*. Medido antes de tocar nada:

    /api/hoy   4,7s la primera vez tras cada reinicio  (paga el texto de Haiku)
               2,0s las siguientes                      (con la cache puesta)

    y dentro de esos 2,0s, CUATRO LECTURAS EN FILA:
       0,5s plan_del_dia + 0,2s alertas + 0,7s negocios + 0,7s bandeja = 2,1s

Tres cosas estaban mal, y son distintas:

  1. Cuatro sistemas que no se esperan entre ellos, consultados uno detras de otro. A la vez manda
     el mas lento (0,7s), no la suma.
  2. El texto de la mañana (3,4s) bloqueaba la pantalla siendo el adorno: lo que se decide son el
     foco y lo urgente.
  3. La cache del texto vivia en MEMORIA, asi que cada despliegue volvia a cobrar los 4,7s y una
     llamada de pago. Ese dia Zeno se reinicio tres veces.

Y en el front, la aplicacion no aparecia hasta que volvia `/api/colas`, que ademas se pedia dos
veces. Ese dato no hace falta para pintar nada.
"""
import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

API = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")
WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
CHAT = (RAIZ / "servicio" / "chat.py").read_text(encoding="utf-8")


def _funcion(fuente: str, nombre: str) -> str:
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nombre:
            return ast.unparse(n)
    raise AssertionError(f"no existe {nombre}")


# ------------------------------------------------------------------ 1. a la vez, no en fila

def test_las_lecturas_de_la_mañana_van_A_LA_VEZ():
    """LO QUE COSTABA 2,1s. Son cuatro sistemas distintos que no dependen unos de otros."""
    cuerpo = _funcion(API, "api_hoy")
    assert "asyncio.gather" in cuerpo, "vuelven a ir en fila: 2,1s en vez de 0,7s"
    assert cuerpo.count("asyncio.to_thread") >= 4, (
        "alguna lectura ha vuelto a la fila. Son sincronas (urllib): sin to_thread, 'a la vez' es "
        "mentira y corren una detras de otra en el mismo hilo")


def test_una_lectura_caida_no_tumba_la_mañana():
    """Poner las cuatro a la vez no puede costar robustez: si una revienta, la pantalla sale con
    las otras tres y se dice lo que falta. Sin `return_exceptions` una sola caida se lleva todo."""
    cuerpo = _funcion(API, "api_hoy")
    assert "return_exceptions=True" in cuerpo
    assert "_saca" in cuerpo


# ------------------------------------------------------------------ 2. el adorno no bloquea

def test_el_texto_de_la_mañana_NO_bloquea_la_pantalla():
    """3,4s medidos por una llamada a Haiku, para un texto que es el adorno. La pantalla sale con
    sus datos y el texto se recoge despues."""
    cuerpo = _funcion(API, "api_hoy")
    assert "resumen_ya_hecho" in cuerpo, "vuelve a esperar al modelo dentro de la pantalla"
    assert "resumen_de_la_manana" not in cuerpo, (
        "llama al modelo desde el endpoint: eso son 3,4s de espera para quien abre")
    assert "resumen_en_camino" in cuerpo


def test_hay_donde_recoger_el_texto_cuando_este():
    """Si no existiera esta ventanilla, el texto se escribiria y no lo veria nadie hasta recargar."""
    cuerpo = _funcion(API, "api_hoy_resumen")
    assert "resumen_ya_hecho" in cuerpo and "en_camino" in cuerpo


def test_que_el_texto_falle_NO_se_calla():
    """Lo que este test defiende desde el principio. Ahora el texto se escribe por detras, asi que
    el fallo ya no puede llegar en la respuesta de /api/hoy: tiene que llegar a quien pregunte por
    el resumen. Lo que no cambia es que se dice."""
    assert "_FALLO_RESUMEN" in API
    cuerpo = _funcion(API, "api_hoy_resumen")
    assert "fallos" in cuerpo and "_FALLO_RESUMEN" in cuerpo
    # Y CADA camino de error deja el motivo, no solo uno. Son tres (el tope diario, la falta de
    # clave y cualquier otro fallo), y el ultimo es el que tapa una caida de Anthropic: si ese se
    # callara, el hueco quedaria mudo y los otros dos tests seguirian en verde.
    arranca = _funcion(API, "_arranca_el_resumen")
    assert arranca.count("_FALLO_RESUMEN['por_que'] =") >= 2, (
        "algun camino de error se traga el motivo: " + arranca)


def test_no_se_escriben_DOS_resumenes_a_la_vez():
    """Cada uno cuesta una llamada de pago. Sin el cerrojo, recargar la pantalla mientras se
    escribe el primero pediria otro."""
    assert "_ESCRIBIENDO = threading.Lock()" in API
    cuerpo = _funcion(API, "_arranca_el_resumen")
    assert "acquire(blocking=False)" in cuerpo, "sin esto, dos recargas son dos llamadas de pago"


# ------------------------------------------------------------------ 3. la cache aguanta

def test_la_cache_del_resumen_sobrevive_a_un_reinicio():
    """EL COSTE ESCONDIDO. En memoria, cada despliegue volvia a cobrar 4,7s y una llamada. El
    diario ya vivia en /datos por esta misma razon."""
    assert "_CACHE" in CHAT and "/datos/" in CHAT
    assert "_guarda_cache" in _funcion(CHAT, "resumen_de_la_manana")


def test_una_cache_rota_no_tumba_la_mañana():
    """Un fichero a medias (un reinicio en mitad de la escritura) no puede dejar sin pantalla."""
    cuerpo = _funcion(CHAT, "_lee_cache")
    assert "except" in cuerpo, "una cache ilegible tumbaria la pantalla de la mañana"


def test_leer_el_resumen_hecho_NO_llama_al_modelo():
    """Esta es la funcion que usa la pantalla para salir rapido. Si llamara al modelo, no habria
    ganado nada: solo se habria movido la espera de sitio."""
    cuerpo = _funcion(CHAT, "resumen_ya_hecho")
    assert "urlopen" not in cuerpo and "resumen_de_la_manana" not in cuerpo


# ------------------------------------------------------------------ 4. la pantalla aparece ya

def test_la_aplicacion_no_espera_a_nadie_para_aparecer():
    """Aqui se esperaba a `/api/colas` para ENTRAR. Ese dato no hace falta para pintar nada."""
    assert "if (token) dentro(token);" in WEB, "vuelve a esperar una peticion para mostrarse"
    assert "cargaColasAbribles().then(() => dentro(token))" not in WEB


def test_primero_se_enseña_y_despues_se_pide():
    """El orden dentro de `dentro()`: si las peticiones van antes de quitar el login, la pantalla
    se queda en blanco mientras tanto aunque no dependa de ellas."""
    i = WEB.index("function dentro(t) {")
    cuerpo = WEB[i:i + 900]
    assert cuerpo.index('$("#app").hidden = false') < cuerpo.index("cargaColasAbribles"), (
        "vuelve a pedir antes de enseñar")


def test_las_colas_abribles_no_se_piden_DOS_veces():
    """Se pedian dos: una para entrar y otra dentro. La misma lista, dos viajes."""
    assert WEB.count("cargaColasAbribles()") == 2, (
        "una es la definicion y otra la llamada: mas de eso es pedirlo repetido")


def test_el_hueco_del_resumen_se_recoge():
    """LA PIEZA ESCRITA QUE NADIE LLAMA, que es el fallo que ya mordio hoy. Si `esperaElResumen`
    estuviera definida y no se llamara, el hueco quedaria mudo para siempre."""
    assert WEB.count("esperaElResumen") == 2, "definida pero no llamada (o al reves)"
    assert "if (d.resumen_en_camino) esperaElResumen();" in WEB


def test_si_el_texto_no_sale_el_hueco_no_se_queda_mudo():
    """SE ACOTA A LA FUNCION, no a los 1400 caracteres siguientes: ahi dentro cae el principio de
    `cargaHoy`, que tambien pinta `aviso-fallo`, y el test pasaba aunque se quitara el de aqui."""
    i = WEB.index("async function esperaElResumen")
    cuerpo = WEB[i:WEB.index("async function cargaHoy")]
    assert "d.fallos" in cuerpo and "aviso-fallo" in cuerpo, (
        "un fallo del texto dejaria el hueco diciendo 'escribiendo el resumen' para siempre")
    assert "hueco.remove()" in cuerpo
