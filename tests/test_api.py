# -*- coding: utf-8 -*-
"""El servicio de Zeno no ejecuta nada, y no disimula lo que no pudo leer.

EL CASO. Zeno es la pieza que el operador va a tener en el móvil, y en J4 ejecutará acciones que
publican en su nombre. Hasta entonces la promesa de la fase es que **solo lee**. Una promesa así se
rompe en una línea y ninguna prueba manual la detecta: un POST contra una API que responde 200 se ve
igual de bien en la pantalla.

Y hay un fallo que sería peor que un error visible: que el servicio se coma la caída de un sistema.
Si el cockpit no contesta y Zeno devuelve la lista de GutLyn sin decir nada, el operador lee "hay una
cosa pendiente" cuando la verdad es "hay una que he podido ver". Con eso se toman decisiones.

Puros: sin red. Se sustituyen el lector y la sesión.
"""
import ast
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fastapi = pytest.importorskip("fastapi", reason="el servicio necesita fastapi")
from fastapi.testclient import TestClient            # noqa: E402

import lector                                        # noqa: E402
from servicio import api as api_mod, sesion          # noqa: E402

cliente = TestClient(api_mod.app)
CABECERA = {"Authorization": "Bearer jwt-bueno"}


@pytest.fixture(autouse=True)
def _sesion_valida(monkeypatch):
    monkeypatch.setattr(sesion, "quien_es",
                        lambda t, ahora=None: sesion.Quien("u1", "owner", "yo@zenvrax.com"))
    # El recuento por cola sale a la red en produccion: aqui se silencia salvo que el test lo pise.
    monkeypatch.setattr(lector, "pendiente_completo", lambda: ([], []))
    yield
    sesion.limpiar_cache()


# ---------------------------------------------------------------- no ejecuta

def test_el_servicio_no_hace_ninguna_llamada_que_no_sea_get_hacia_los_dos_sistemas():
    """Del árbol del lector, que es quien habla con el cockpit y con Xrise. El servicio es una
    fachada: si alguien mete aquí un POST hacia fuera, deja de ser la fase que no rompe nada."""
    arbol = ast.parse((RAIZ / "lector.py").read_text(encoding="utf-8"))
    metodos = [kw.value.value for n in ast.walk(arbol) if isinstance(n, ast.Call)
               for kw in n.keywords if kw.arg == "method" and isinstance(kw.value, ast.Constant)]
    assert metodos and set(metodos) == {"GET"}, f"el lector hace peticiones que no son GET: {set(metodos)}"


def test_no_hay_ningun_endpoint_que_ejecute_una_accion():
    """Los únicos POST del servicio son entrar, salir y el chat (apagado). Un POST que dispare una
    acción del catálogo sería J4 entrando por la puerta de atrás."""
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))
    posts = []
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for d in n.decorator_list:
            f = d.func if isinstance(d, ast.Call) else d
            if isinstance(f, ast.Attribute) and f.attr in ("post", "put", "patch", "delete"):
                posts.append(n.name)
    # La lista es cerrada a propósito: para añadir un POST hay que venir aquí y escribir por qué, y
    # así un endpoint que dispare una acción no puede colarse sin que nadie lo lea.
    permitidos = [
        "chat",              # gasta API, y nace apagado
        "google_conectar",   # devuelve la dirección de Google; no toca ni una cola
        "google_olvidar",    # retira un permiso de Google; solo quita, nunca ejecuta
        "entrar_con_clave",  # cambia la clave propia por un token; no toca ninguna cola
        "login", "login_2fa", "salir",
    ]
    assert sorted(posts) == sorted(permitidos), (
        f"endpoints que escriben y no deberían existir todavía: {sorted(posts)}")


def test_ningun_endpoint_llama_al_catalogo_ni_dispara_una_accion():
    """El guardián de arriba mira los VERBOS, y eso dejó de bastar al aparecer los POST de Google.

    Lo que de verdad no puede pasar es que el servicio ejecute una acción de las colas, y eso se
    reconoce por a quién llama, no por si es POST: un webhook de aprobación de n8n se dispara con un
    GET (ver la regla del enlace que publica). Así que aquí se mira que nadie llame a nada que
    ejecute, con cualquier verbo.
    """
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))

    def nombre(n):
        """El nombre con puntos de lo que se llama: `google.pide`, `urlopen`, `sesion.entrar`."""
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.Attribute):
            return (nombre(n.value) + "." if nombre(n.value) else "") + n.attr
        return ""

    llamadas = {nombre(n.func) for n in ast.walk(arbol) if isinstance(n, ast.Call)}
    # Se mira lo que se LLAMA, no el texto del fichero: los comentarios de este módulo hablan de no
    # ejecutar acciones, y buscar la palabra suelta haría saltar el guardián por su propia
    # documentación.
    for mala in ("urlopen", "requests.post", "requests.get", "httpx.post", "httpx.put",
                 "httpx.delete", "catalogo.ejecuta", "ejecutor.ejecuta"):
        assert mala not in llamadas, (
            f"api.py llama a {mala!r}: el servicio no sale a ejecutar nada, solo lee por sus módulos")
    # Y de los módulos de Google, solo lo que lee o gestiona el permiso. Cualquier otra función
    # nueva de `google` tiene que pasar por aquí antes de ser alcanzable desde la web.
    de_google = {c for c in llamadas if c.startswith("google.")}
    assert de_google <= {"google.conectadas", "google._cliente", "google.enlace_para_autorizar",
                         "google.guarda_permiso", "google.olvida", "google.CUENTAS.items"}, (
        f"api.py expone de google algo no previsto: {de_google}")


def test_el_chat_nace_apagado_porque_gasta_dinero():
    """Medido: ~$0,006 por pregunta. Encenderlo por defecto sería gastar sin haberlo puesto delante
    del operador, que es justo lo que su regla prohíbe."""
    r = cliente.post("/api/chat", headers=CABECERA, json={"texto": "hola"})
    assert r.status_code == 501
    assert "tu OK" in r.json()["detail"], "el mensaje tiene que decir POR QUÉ está apagado"
    assert api_mod.CHAT_ACTIVO is False, "de serie, apagado"


# ---------------------------------------------------------------- no disimula

def test_los_fallos_viajan_siempre_aunque_esten_vacios(monkeypatch):
    """Si `fallos` solo apareciera cuando hay alguno, el front tendría que adivinar si una lista
    corta es "hay poco" o "no he podido leer la mitad"."""
    monkeypatch.setattr(lector, "pendientes", lambda: ([], []))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()
    assert "fallos" in d and d["fallos"] == []


def test_un_sistema_caido_sale_en_la_respuesta(monkeypatch):
    monkeypatch.setattr(lector, "pendientes",
                        lambda: ([], ["Zenvrax (cockpit): HTTP 502 en /notifications"]))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()
    assert d["fallos"], "la caída no puede desaparecer entre la lectura y la respuesta"


def test_cada_pendiente_lleva_si_publica_y_si_cuesta(monkeypatch):
    """Es lo que Zeno aporta sobre mirar las dos pantallas. Sin estos campos, el front no puede
    marcar lo irreversible ni lo que gasta."""
    p = lector.Pendiente(negocio="GutLyn", titulo="Post", cuerpo="", acciones=[
        lector.Accion("Aprobar y publicar", "claire.aprobar_y_publicar", "publica", False),
        lector.Accion("Regenerar", "claire.regenerar", "cambia_estado", True)])
    monkeypatch.setattr(lector, "pendientes", lambda: ([p], []))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()["pendientes"][0]
    assert d["publica_algo"] is True and d["cuesta_dinero"] is True
    assert d["acciones"][0]["efecto"] == "publica"


def test_la_busqueda_dice_en_que_modo_respondio(monkeypatch):
    """Contestar "no hay nada" con el servicio de significado caído es mentir con cara de certeza."""
    monkeypatch.setattr(lector, "documentacion", lambda q: ([], "texto", []))
    d = cliente.get("/api/buscar?q=precios", headers=CABECERA).json()
    assert d["modo"] == "texto"


# ---------------------------------------------------------------- caído no es lo mismo que fuera

def test_el_cockpit_caido_devuelve_503_y_no_401(monkeypatch):
    """EL TEST QUE IMPORTA. Con 401 el front borra el token y echa al operador al login cada vez que
    el cockpit se reinicia. Es el incidente de agosto de 2026 en el propio cockpit."""
    def cae(t, ahora=None):
        raise sesion.CockpitNoResponde("timeout")
    monkeypatch.setattr(sesion, "quien_es", cae)
    assert cliente.get("/api/pendientes", headers=CABECERA).status_code == 503


def test_una_sesion_invalida_si_devuelve_401(monkeypatch):
    def fuera(t, ahora=None):
        raise sesion.NoAutenticado("token malo")
    monkeypatch.setattr(sesion, "quien_es", fuera)
    assert cliente.get("/api/pendientes", headers=CABECERA).status_code == 401


def test_sin_cabecera_no_se_entra(monkeypatch):
    def fuera(t, ahora=None):
        raise sesion.NoAutenticado("sin token")
    monkeypatch.setattr(sesion, "quien_es", fuera)
    for ruta in ("/api/pendientes", "/api/buscar?q=hola", "/api/yo"):
        assert cliente.get(ruta).status_code == 401, f"{ruta} deja pasar sin sesión"


def test_la_salud_no_pide_sesion():
    """La mira el despliegue para saber si el contenedor vive: pedirle sesión lo dejaría siempre en
    rojo y el arranque no se daría nunca por bueno."""
    r = cliente.get("/api/salud")
    assert r.status_code == 200 and r.json()["ok"] is True


# ---------------------------------------------------------------- el chat, con Haiku y con tope

def test_el_chat_usa_haiku_y_no_sonnet():
    """El operador: *"el modelo debería ser haiku"*. Medido sobre 30 días reales del ecosistema,
    Haiku sale a $0,0017 por llamada y Sonnet a $0,0079: 4,5 veces más caro para contestar sobre un
    contexto que Zeno ya tiene delante. La voz la pone el prompt, no el modelo."""
    from servicio import chat as chat_mod
    assert "haiku" in chat_mod.MODELO.lower(), (
        f"el chat usa {chat_mod.MODELO}: encarece cada pregunta sin mejorar la respuesta")


def test_el_chat_tiene_tope_diario():
    """Es la única pieza de Zeno cuyo coste lo decide el uso y no el sistema. Sin tope, una tarde de
    curiosidad se convierte en una factura que nadie vio venir."""
    from servicio import chat as chat_mod
    assert 0 < chat_mod.TOPE_DIARIO <= 200, f"tope raro: {chat_mod.TOPE_DIARIO}"


def test_cada_respuesta_dice_lo_que_ha_costado(monkeypatch):
    """Sin la cifra en pantalla, el gasto solo se ve en la factura de fin de mes."""
    from servicio import chat as chat_mod
    import inspect
    fuente = inspect.getsource(chat_mod.responde)
    for campo in ("coste_usd", "preguntas_hoy", "tope_diario", "modelo"):
        assert campo in fuente, f"la respuesta del chat no dice {campo}"


def test_el_chat_no_promete_ejecutar():
    """Zeno todavía no ejecuta: eso es J4. Si el prompt no se lo prohíbe, el modelo dirá que sí
    puede, y el operador se quedará esperando algo que no va a pasar."""
    from servicio import chat as chat_mod
    assert "no puedes" in chat_mod.SISTEMA or "todavía no puedes" in chat_mod.SISTEMA
    assert "Inventar" in chat_mod.SISTEMA, "el prompt tiene que prohibir inventar cifras"


def test_la_respuesta_no_sale_con_asteriscos_ni_raya_larga():
    """DOS REGLAS DEL OPERADOR, y el prompt no las garantiza.

    En la primera prueba real, con la prohibición escrita en el sistema, el modelo contestó
    `**Hoy tienes pendiente:**`. Un prompt es una petición; esto es la garantía.
    """
    from servicio.chat import _limpia
    assert _limpia("**Hoy tienes pendiente:**") == "Hoy tienes pendiente:"
    assert _limpia("los *44* posts") == "los 44 posts"
    assert _limpia("una cosa — y otra") == "una cosa, y otra"
    assert _limpia("rango 10–20 aqui") == "rango 10, 20 aqui"
    assert _limpia("sin nada raro") == "sin nada raro", "no puede estropear lo que ya estaba bien"


def test_la_limpieza_se_aplica_de_verdad_a_la_respuesta():
    """Que la función exista no sirve de nada si `responde` no la llama."""
    import inspect
    from servicio import chat as chat_mod
    assert "_limpia(texto)" in inspect.getsource(chat_mod.responde)


def test_el_chat_recibe_el_estado_de_los_negocios_y_las_ventas():
    """EL FALLO QUE VIO EL OPERADOR. Preguntó *"situación actual de ventas de GutLyn"* y el chat
    contestó que no tenía el dato, teniendo Zeno la forma de leerlo: el contexto solo llevaba lo
    pendiente y las colas.

    Un asistente que no sabe cómo va el negocio no es un asistente, es una bandeja.
    """
    import inspect
    from servicio import api as m
    fuente = inspect.getsource(m.chat)
    assert "lector.estado()" in fuente, "el chat no pide el estado de los negocios"
    assert "lector.ventas_gutlyn()" in fuente, "el chat no pide las ventas"
    assert "estado, ventas" in fuente, "los pide pero no se los pasa al modelo"


def test_el_contexto_pinta_los_kpis_con_su_alerta():
    """Si los KPIs llegaran sin la marca de alerta, el chat diría "beneficio -99" como un dato más,
    cuando el cockpit ya lo tiene señalado como malo."""
    from servicio.chat import _contexto
    estado = {"zenvrax": {"negocios": [{"nombre": "Zenvrax IO", "sub": "c", "kpis": [
        {"k": "Beneficio/mes", "v": "$-99", "alerta": "bad"}]}]}}
    texto = _contexto([], [], [], [], estado, None)
    assert "Beneficio/mes: $-99" in texto and "(MAL)" in texto


def test_un_negocio_sin_cifras_dice_por_que():
    """GutLyn no tiene ventas registradas todavía. Pintarlo vacío haría que el chat dijera que no
    sabe, cuando el dato es que aún no hay nada conectado."""
    from servicio.chat import _contexto
    estado = {"zenvrax": {"negocios": [{"nombre": "GutLyn+", "sub": "e", "kpis": [],
                                        "nota": "Sin ventas registradas todavia"}]}}
    assert "Sin ventas registradas" in _contexto([], [], [], [], estado, None)


def test_un_cero_en_ventas_no_se_presenta_como_falta_de_dato():
    """EL SEGUNDO INTENTO DEL MISMO FALLO (2026-09-27).

    Primero el chat no recibía las ventas. Se las di en JSON crudo "para no decidir por el modelo",
    y ante un objeto lleno de `0.0` y `null` volvió a contestar *"no tengo datos de ventas"*
    cuando el dato SÍ estaba y decía cero.

    Un cero no es la ausencia de un dato: es una respuesta, y aquí la importante. Se comprueba en
    los dos sitios, porque hacía falta arreglar los dos: el texto que se le pasa y la regla.
    """
    from servicio.chat import _ventas, SISTEMA
    texto = _ventas({"resumen": {"period_days": 30, "revenue": 0.0, "orders": 0}})
    assert "ingresos: $0.00" in texto, "la cifra tiene que aparecer, no desaparecer por ser cero"
    assert "TODO A CERO" in texto and "no falta el dato" in texto
    assert "Un CERO es una respuesta" in SISTEMA, (
        "sin la regla en el prompt, el modelo vuelve a leer los ceros como que no sabe")
    # Y la induccion que lo causaba: decirle que GutLyn "se gestiona desde Xrise" hacia que
    # repitiera "miralo en Xrise" en vez de leer las cifras que tenia delante.
    assert "que se gestiona desde Xrise" not in SISTEMA
    assert "ESTAN en el contexto" in SISTEMA


def test_las_ventas_no_se_pasan_como_json_crudo():
    """El JSON con veinte claves y la mitad a null es lo que confundió al modelo."""
    import inspect
    from servicio import chat as m
    fuente = inspect.getsource(m._contexto)
    assert "_ventas(ventas)" in fuente
    assert "json.dumps(ventas" not in fuente, "las ventas vuelven a ir en crudo"


def test_responde_le_pasa_de_verdad_el_estado_al_contexto():
    """EL FALLO QUE HIZO FALTA TRES INTENTOS (2026-09-27).

    `responde()` recibía `estado` y `ventas` y NO se los pasaba a `_contexto()`: el reemplazo de esa
    línea nunca se aplicó y yo no lo comprobé. Los tests que tenía miraban que el endpoint pidiera
    el estado y que `_contexto` supiera pintarlo, pero ninguno miraba el ÚNICO punto donde se unen
    las dos mitades. Por eso pasaban con el fallo dentro.

    Se ve preguntándole por la caja: el contexto la tiene y el chat decía que no.
    """
    import inspect
    from servicio import chat as m
    fuente = inspect.getsource(m.responde)
    assert "_contexto(pendientes, colas, fallos, documentos, estado, ventas)" in fuente, (
        "responde() recibe el estado y no se lo pasa al contexto: el chat se queda ciego")


# ---------------------------------------------------------------- la vuelta de Google

def test_la_vuelta_de_google_sin_vale_no_ata_ninguna_cuenta(monkeypatch):
    """EL TEST QUE IMPORTA de esta tanda. La vuelta de Google llega por el navegador, o sea SIN la
    cabecera del token, así que es el único endpoint sin sesión de todo el servicio.

    Si aceptara cualquier `state`, cualquiera que conociera la dirección podría atar su propia cuenta
    de Google al Zeno del operador, y a partir de ahí Zeno leería el correo de un desconocido y lo
    enseñaría como si fuera suyo. Lo que lo impide es el vale de un solo uso que se apunta al empezar
    desde dentro.
    """
    llamadas = []
    monkeypatch.setattr(api_mod.google, "guarda_permiso",
                        lambda n, c: llamadas.append((n, c)) or {"cuenta": "x"})
    r = cliente.get("/api/google/vuelta?code=robado&state=inventado")
    assert r.status_code == 400
    assert not llamadas, "se ha intentado guardar un permiso sin haber empezado desde Zeno"


def test_un_vale_sirve_una_sola_vez(monkeypatch):
    """Reutilizar el vale sería poder repetir la vuelta: el segundo intento tiene que caer."""
    monkeypatch.setattr(api_mod.google, "guarda_permiso",
                        lambda n, c: {"cuenta": api_mod.google.CUENTAS[n]})
    vale = api_mod._vale_nuevo("zenvrax")
    assert cliente.get(f"/api/google/vuelta?code=c&state={vale}").status_code == 200
    assert cliente.get(f"/api/google/vuelta?code=c&state={vale}").status_code == 400


def test_un_vale_caducado_no_vale(monkeypatch):
    monkeypatch.setattr(api_mod.google, "guarda_permiso", lambda n, c: {"cuenta": "x"})
    vale = api_mod._vale_nuevo("zenvrax")
    api_mod._VALES[vale] = ("zenvrax", 0.0)          # nacido en 1970
    assert cliente.get(f"/api/google/vuelta?code=c&state={vale}").status_code == 400


def test_si_google_dice_que_no_se_enseña_el_motivo_y_no_se_guarda_nada(monkeypatch):
    monkeypatch.setattr(api_mod.google, "guarda_permiso",
                        lambda n, c: pytest.fail("no se puede guardar nada si Google dijo que no"))
    r = cliente.get("/api/google/vuelta?error=access_denied")
    assert r.status_code == 200 and "access_denied" in r.text


def test_las_cuentas_dicen_si_les_falta_el_cliente(monkeypatch):
    """Sin cliente OAuth el botón no puede funcionar. Enseñarlo igual sería mandar al operador a
    comerse un error de Google sin saber por qué."""
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {})
    monkeypatch.setattr(api_mod.google, "_cliente", lambda n: ("", ""))
    d = cliente.get("/api/google/cuentas", headers=CABECERA).json()
    assert len(d["cuentas"]) == 2
    assert all(c["configurada"] is False and c["conectada"] is False for c in d["cuentas"])


def test_conectar_una_cuenta_que_no_existe_da_404():
    assert cliente.post("/api/google/conectar?negocio=acme",
                        headers=CABECERA).status_code == 404


def test_el_enlace_de_conectar_lleva_el_vale(monkeypatch):
    monkeypatch.setattr(api_mod.google, "enlace_para_autorizar",
                        lambda n, estado="": "https://g/?x=1&state=" + estado)
    d = cliente.post("/api/google/conectar?negocio=gutlyn", headers=CABECERA).json()
    assert d["enlace"].count("state=") == 1, "dos veces state y Google bloquea el acceso"
    vale = d["enlace"].split("state=")[1]
    assert api_mod._VALES[vale][0] == "gutlyn", "el vale tiene que recordar de qué cuenta era"


def test_lo_personal_necesita_sesion(monkeypatch):
    """Es correo personal: es el endpoint del servicio donde una fuga duele mas. La fixture de este
    fichero da por buena cualquier sesion, asi que aqui se devuelve la de verdad para comprobar que
    el endpoint la pide."""
    def no(token, ahora=None):
        raise sesion.NoAutenticado("sin token")
    monkeypatch.setattr(sesion, "quien_es", no)
    assert cliente.get("/api/personal").status_code == 401


def test_lo_personal_lleva_los_fallos_aunque_haya_correo(monkeypatch):
    """Mismo motivo que en pendientes: una bandeja corta sin aviso se lee como "tengo poco correo"
    cuando la verdad puede ser "falta una cuenta entera"."""
    monkeypatch.setattr(api_mod.personal, "bandeja",
                        lambda: ({"correos": [{"asunto": "uno"}], "agenda": [], "cuentas": {}},
                                 ["ghidalgo@gutlyn.com: sin conectar todavia"]))
    d = cliente.get("/api/personal", headers=CABECERA).json()
    assert len(d["correos"]) == 1 and d["fallos"]
