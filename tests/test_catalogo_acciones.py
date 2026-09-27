# -*- coding: utf-8 -*-
"""El asistente no puede inventarse una llamada ni confundir abrir con publicar.

EL CASO. Solo el cockpit tiene 190 rutas que mutan, y Xrise las suyas. Un asistente al que se le da
esa API y se le pide que actue elige la llamada, y elegir es adivinar. La fase J1 del plan cierra la
lista: 33 acciones, las que YA son botones en las dos colas, cada una con su contrato.

Y hay un detalle que no se ve leyendo el codigo por encima, y es el que justifica la fase: TRES de
esas acciones publican de verdad y estan escritas EXACTAMENTE igual que un enlace a una guia en
HTML (`{"url": ".../webhook/linkedin-approve?id=..."}`, un GET). Nada en el dato las distingue de
`{"url": "https://magnets.zenvrax.com/.../guia.html"}`. Un asistente que dedujera el efecto del
verbo publicaria en LinkedIn creyendo que abre una pantalla.

Lo que estos tests protegen son las formas de romper esto sin que nada lance una excepcion: un boton
nuevo sin declarar, un destino que ya no existe, una accion que publica marcada como reversible, y
una que gasta API sin decirlo.

Puros: leen ficheros, no tocan base de datos ni red.
"""
import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import catalogo as C                                    # noqa: E402
from catalogo.recolector import RAICES, sistemas_ausentes   # noqa: E402

#: Donde estan los routers de cada sistema, para comprobar que los destinos existen de verdad.
ROUTERS = {"cockpit": "cockpit/api/app/routers", "xrise": "saas/api/app/routers"}


def _hueco(ruta: str) -> str:
    """`/a/{pid}/b` y `/a/{post_id}/b` son la misma ruta: el nombre del parametro no cuenta."""
    return re.sub(r"\{[^}]*\}", "{}", ruta)


def _rutas_declaradas(sistema: str) -> set[tuple[str, str]]:
    """(VERBO, ruta) de cada endpoint de ese sistema, con el prefijo de su router ya puesto."""
    carpeta = RAICES[sistema] / ROUTERS[sistema]
    fuera: set[tuple[str, str]] = set()
    for fichero in sorted(carpeta.glob("*.py")):
        src = fichero.read_text(encoding="utf-8", errors="replace")
        arbol = ast.parse(src)
        prefijos = {""}
        for nodo in ast.walk(arbol):
            # APIRouter(prefix="/marketing", ...) — puede haber mas de un router por fichero
            if (isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") == "APIRouter"):
                for kw in nodo.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefijos.add(kw.value.value)
        for m in re.finditer(r"@(\w+)\.(get|post|patch|put|delete)\(\s*[\"']([^\"']+)", src):
            verbo, camino = m.group(2).upper(), m.group(3)
            for p in prefijos:
                fuera.add((verbo, _hueco(p + camino)))
    return fuera


# ---------------------------------------------------------------- el catalogo esta completo

def test_ningun_boton_se_queda_sin_contrato():
    """Si alguien añade un boton a una cola y no lo declara, el asistente no lo veria y el operador
    lo tendria en la aplicacion y no en el asistente, sin saber por que. Mejor que falle aqui."""
    faltan = C.sin_contrato()
    assert faltan == [], "botones sin contrato declarado:\n  " + "\n  ".join(faltan)


def test_ningun_contrato_se_queda_sin_boton():
    """Un contrato huerfano significa que el boton cambio de destino o de etiqueta: el asistente
    perdio esa accion Y arrastra la descripcion de algo que ya no existe."""
    if sistemas_ausentes():
        return
    huerfanos = C.contratos_huerfanos()
    assert huerfanos == [], "contratos que ya no corresponden a ningun boton:\n  " + "\n  ".join(huerfanos)


def test_cada_accion_tiene_un_nombre_propio():
    """El `op` es como el asistente nombra la accion. Dos acciones distintas con el mismo nombre
    hacen que ejecute la que no era."""
    ops = [a.op for a in C.catalogo()]
    repetidos = sorted({o for o in ops if ops.count(o) > 1})
    assert not repetidos, f"nombres repetidos: {repetidos}"


# ---------------------------------------------------------------- los destinos existen

def test_los_destinos_de_la_api_propia_existen_de_verdad():
    """EL TEST DE LA FASE. Un destino que ya no existe da 404 al pulsar, y el asistente diria "hecho"
    si no mira. Aqui se comprueba contra los routers, no contra la memoria."""
    for sistema in ("cockpit", "xrise"):
        if sistema in sistemas_ausentes():
            continue
        declaradas = _rutas_declaradas(sistema)
        for a in C.ejecutables([sistema]):
            if not str(a.destino).startswith("/"):
                continue                      # webhook de n8n o enlace externo: no es su API
            assert (a.verbo, _hueco(a.destino)) in declaradas, (
                f"{a.op}: {a.verbo} {a.destino} no existe en los routers de {sistema} "
                f"(cola en la linea {a.linea})")


def test_lo_que_no_es_de_la_api_propia_va_por_webhook_o_enlace():
    """Un destino que no empieza por `/` y tampoco es una URL completa seria una cadena a medias que
    el asistente no sabria a donde mandar."""
    for a in C.catalogo():
        d = str(a.destino)
        assert d.startswith("/") or d.startswith("http") or "{" in d or d == "<dinamico>", (
            f"{a.op}: destino que no se sabe resolver: {d!r}")


# ---------------------------------------------------------------- lo peligroso esta marcado

def test_lo_que_sale_al_mundo_no_se_declara_reversible_ni_sin_confirmar():
    """Son las 8 que publican en LinkedIn, X, Meta o por correo. Si una se cuela como reversible, el
    asistente la ejecutaria sin preguntar y no hay vuelta atras."""
    for a in C.catalogo():
        if a.efecto == C.PUBLICA:
            assert not a.reversible, f"{a.op}: publica y se declara reversible"
            assert a.confirmar, f"{a.op}: publica y no pide confirmacion"


def test_toda_regeneracion_declara_que_cuesta_dinero():
    """Regenerar pide otro texto a Claude, o sea gasta. Hay una regla dura sobre no gastar sin
    permiso, y el asistente no puede respetarla si el catalogo no le dice cual gasta. Se comprueba
    por el NOMBRE y por la etiqueta, para que una regeneracion nueva no entre sin marcar."""
    for a in C.catalogo():
        parece = "regenerar" in a.op or "Regenerar" in (a.etiqueta or "")
        if parece:
            assert a.coste_api, f"{a.op}: regenera y no declara coste_api"


def test_lo_que_solo_abre_no_puede_escribir():
    """Las 13 que abren una pantalla no son acciones: son enlaces. Si una se marcara como que abre
    pero llevara un POST con cuerpo, el asistente la ejecutaria sin confirmar."""
    for a in C.catalogo():
        if a.efecto == C.ABRE:
            assert a.verbo == "GET", f"{a.op}: dice que solo abre y usa {a.verbo}"
            assert not a.cuerpo, f"{a.op}: dice que solo abre y manda un cuerpo"


def test_las_tres_que_publican_por_un_get_estan_declaradas_como_tales():
    """El hallazgo de la fase, escrito como test: son webhooks de n8n por GET indistinguibles de un
    enlace. Si alguna perdiera su contrato, volveria a parecer un enlace inocente."""
    por_webhook = [a for a in C.catalogo()
                   if "/webhook/" in str(a.destino) and a.muta]
    ops = sorted(a.op for a in por_webhook)
    assert ops == ["linkedin.aprobar_y_publicar", "linkedin.regenerar",
                   "newsletter.confirmar_publicada"], (
        f"cambiaron las acciones que mutan por webhook GET: {ops}. "
        "Si es a proposito, actualiza este test Y comprueba que el asistente sigue distinguiendolas "
        "de un enlace")
    for a in por_webhook:
        assert a.confirmar, f"{a.op}: muta por un GET que parece un enlace y no pide confirmacion"


def test_se_sabe_cuales_no_tienen_ninguna_guarda():
    """No es un fallo tener acciones sin guarda: es el dato que el asistente necesita para pedir
    confirmacion. Lo que seria un fallo es que el numero creciera sin que nadie lo note.

    Se cuenta POR SISTEMA y solo se comprueban los presentes. Contando el total, este test se ponia
    rojo en CI, donde el repo de Xrise no esta y por tanto faltan sus 5: un guard que falla por que
    falte un repo hermano acaba desactivado, y entonces ya no guarda nada.
    """
    esperado = {"cockpit": 6, "xrise": 5}
    ausentes = sistemas_ausentes()
    for sistema, cuantas in esperado.items():
        if sistema in ausentes:
            continue
        sin_guarda = sorted(a.op for a in C.catalogo([sistema])
                            if a.muta and a.guarda.startswith("ninguna"))
        assert len(sin_guarda) == cuantas, (
            f"{sistema}: cambio el numero de acciones que mutan sin ninguna guarda "
            f"({len(sin_guarda)}, se esperaban {cuantas}): " + ", ".join(sin_guarda))


# ---------------------------------------------------------------- el catalogo que viaja dentro

def test_el_catalogo_congelado_esta_al_dia():
    """Dentro del contenedor no están los dos repos, así que Zeno usa un catálogo CONGELADO. Si se
    desincroniza, el operador ve todos los botones marcados "sin contrato", que parece un fallo del
    sistema y no una falta de datos.

    Se descubrió escribiendo el Dockerfile, no en producción. Se regenera con:
        python lab/zeno/catalogo/congelar.py
    """
    import json
    if sistemas_ausentes():
        return                     # sin los repos no hay con qué comparar
    fichero = Path(C.__file__).resolve().parent / "congelado.json"
    assert fichero.exists(), "falta congelado.json: Zeno saldría sin catálogo dentro del contenedor"
    congelado = json.loads(fichero.read_text(encoding="utf-8"))
    vivas = {a.op for a in C.catalogo()}
    guardadas = {a["op"] for a in congelado["acciones"]}
    assert vivas == guardadas, (
        "el catálogo congelado no cuadra con las colas.\n"
        f"  solo en las colas: {sorted(vivas - guardadas)}\n"
        f"  solo congeladas:   {sorted(guardadas - vivas)}\n"
        "  regenera con: python lab/zeno/catalogo/congelar.py")


def test_el_congelado_conserva_lo_que_importa():
    """No basta con que estén las mismas acciones: si se perdieran `efecto` o `coste_api`, Zeno
    dejaría de poder avisar de lo irreversible y de lo que gasta."""
    import json
    fichero = Path(C.__file__).resolve().parent / "congelado.json"
    if not fichero.exists():
        return
    for a in json.loads(fichero.read_text(encoding="utf-8"))["acciones"]:
        for campo in ("op", "efecto", "coste_api", "confirmar", "sistema", "etiqueta"):
            assert campo in a, f"al congelar se ha perdido {campo}"


def test_el_catalogo_se_puede_importar_donde_no_estan_los_repos(monkeypatch):
    """EL FALLO QUE TUMBÓ EL CONTENEDOR (2026-09-27), y que estos tests NO cazaban.

    Dentro de la imagen el código vive en `/app/catalogo`, que solo tiene dos padres. El respaldo de
    `_raiz_del_repo` pedía `parents[3]` y lanzaba `IndexError` AL IMPORTAR: el servicio entero no
    arrancaba y el contenedor reiniciaba en bucle. En local nunca falló porque siempre hay
    profundidad de sobra.

    Un repo que no está se responde con "no está", no con una excepción.
    """
    from catalogo import recolector as R
    monkeypatch.setattr(R, "_AQUI", Path("/app/catalogo/recolector.py"))
    R._raiz_del_repo()                      # no puede lanzar
    R._repo_hermano("zenvrax-xrise")        # tampoco


def test_sin_repos_el_catalogo_cae_al_congelado_y_no_a_una_lista_vacia(monkeypatch):
    """Con cero acciones, Zeno marcaría TODOS los botones "sin contrato", que se lee como un fallo
    del sistema y no como una falta de datos."""
    monkeypatch.setattr(C, "sistemas_ausentes", lambda: ["cockpit", "xrise"])
    acciones = C.catalogo()
    assert len(acciones) >= 30, (
        f"sin los repos tendría que usar el catálogo congelado y trajo {len(acciones)} acciones")
