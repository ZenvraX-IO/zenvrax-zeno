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


def test_la_lista_de_endpoints_que_escriben_es_cerrada():
    """Hasta J4 este test decia que NINGUN endpoint ejecutaba una accion, y esa era la promesa de
    la fase. J4 la rompe a proposito: hay uno, `accion_confirmar`, y puede publicar en LinkedIn en
    nombre del operador.

    Asi que el guardian no se quita, se estrecha. La lista sigue cerrada: para añadir un POST hay
    que venir aqui y escribir por que, y asi ninguno se cuela sin que nadie lo lea.
    """
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))
    posts = []
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for d in n.decorator_list:
            f = d.func if isinstance(d, ast.Call) else d
            if isinstance(f, ast.Attribute) and f.attr in ("post", "put", "patch", "delete"):
                posts.append(n.name)
    permitidos = [
        "accion_confirmar",  # EL UNICO que ejecuta algo de las colas. Vale, contrato y PIN
        "accion_proponer",   # lo prepara; no llama a nadie
        "agenda_cambio_confirmar",  # mueve o cancela; PIN si hay invitados
        "agenda_cancelar",   # prepara la cancelacion; no toca Google
        "agenda_confirmar",  # crea la cita; pide un vale
        "agenda_mover",      # prepara el cambio de hora; no toca Google
        "agenda_proponer",   # la prepara; no toca Google
        "avisos_probar",     # manda UN aviso al movil del propio operador
        "avisos_quitar",     # borra una suscripcion
        "avisos_suscribir",  # guarda una suscripcion del navegador
        "chat",              # gasta API
        "rostro_entrar",     # LA PUERTA con Face ID. Firma comprobada contra la clave
                             # publica dada de alta, reto de un solo uso. Emite la sesion
                             # de siempre, que la firma clave.py
        "rostro_alta",       # da de alta un telefono. Exige haber entrado ya
        "rostro_olvidar",    # lo da de baja. Sin esto, una llave no se podria cambiar
        "rostro_abre_pin",   # abre con la cara la ventana de lo irreversible
        "api_orden",         # empareja una frase dicha con algo que ya esta en pantalla y
                             # deja el vale listo. NO ejecuta: confirmar sigue siendo
                             # accion_confirmar, con su diario. Y solo empareja lo
                             # reversible: lo que publica no se hace hablando
        "correo_borrador",   # prepara el borrador; no toca Gmail
        "correo_borrador_confirmar",  # lo guarda en Gmail. NO envia
        "correo_enviar",      # ENVIA de verdad. Sale al mundo y no se recoge: PIN obligatorio,
                             # vale de un solo uso y renglon en el diario, igual que publicar.
                             # Se abrio el 28-sep porque era el unico trabajo diario que empezaba
                             # en Zeno y terminaba en Gmail
        "correo_redactar",   # propone el texto con Haiku; no escribe nada
        "entrar_con_clave",  # cambia la clave propia por un token
        "google_conectar",   # devuelve la direccion de Google; no toca ninguna cola
        "google_olvidar",    # retira un permiso; solo quita
        "correo_ocultar",     # quita un correo de la bandeja de ZENO. No toca Gmail: es
                             # una lista en el volumen, sin permiso nuevo
        "correo_mostrar",     # el deshacer: los devuelve todos
        "api_abrir",          # pide al cockpit o a Xrise un enlace que ENTRA sin
                             # contrasena. No escribe nada aqui: quien decide si lo da
                             # es el sistema de destino, con su propia puerta
        "api_memoria_apunta",  # guarda un apunte en el fichero de Zeno. No sale a la red
        "api_memoria_olvida",  # lo tacha. Sin esto la memoria no se podria corregir
        "api_hilo_borra",    # corta la conversacion guardada. No toca los apuntes
        "login", "login_2fa", "pin_abrir", "salir",
    ]
    assert sorted(posts) == sorted(permitidos), (
        f"endpoints que escriben sin estar declarados: {sorted(set(posts) - set(permitidos))}")


def test_ejecutar_pasa_SIEMPRE_por_el_ejecutor_y_su_contrato():
    """La red no se toca desde api.py. Todo lo que sale va por `ejecutor`, que es quien comprueba
    el contrato, la direccion y el PIN. Si alguien llamara a una url directamente desde aqui, se
    saltaria las cuatro barreras de golpe y el codigo seguiria pareciendo correcto."""
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))
    for f in ast.walk(arbol):
        if not isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if f.name != "accion_confirmar":
            continue
        # Solo el CUERPO: `ast.walk(f)` incluye los decoradores, y `@app.post(...)` aparecia como
        # una llamada a "post", haciendo saltar el guardian por su propia ruta.
        llamadas = {n.func.attr for cuerpo in f.body for n in ast.walk(cuerpo)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert "confirma" in llamadas
        assert "pin_abierto" in llamadas, "sin esto, lo que publica saldria sin PIN"
        assert not llamadas & {"urlopen", "get", "post", "request"}, llamadas
        break
    else:
        raise AssertionError("no existe accion_confirmar")


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
                         "google.guarda_permiso", "google.olvida", "google.CUENTAS.items",
                         "google.CUENTAS.get", "google.ALIAS.items",
                         # `permisos()` solo lee la configuracion: dice que se PIDE, no concede
                         # nada. Se usa para comparar con lo concedido y avisar de lo que falta.
                         "google.permisos", "google.faltan"}, (
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
    monkeypatch.setattr(lector, "pendientes", lambda: ([], [], []))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()
    assert "fallos" in d and d["fallos"] == []


def test_un_sistema_caido_sale_en_la_respuesta(monkeypatch):
    monkeypatch.setattr(lector, "pendientes",
                        lambda: ([], [], ["Zenvrax (cockpit): HTTP 502 en /notifications"]))
    d = cliente.get("/api/pendientes", headers=CABECERA).json()
    assert d["fallos"], "la caída no puede desaparecer entre la lectura y la respuesta"


def test_cada_pendiente_lleva_si_publica_y_si_cuesta(monkeypatch):
    """Es lo que Zeno aporta sobre mirar las dos pantallas. Sin estos campos, el front no puede
    marcar lo irreversible ni lo que gasta."""
    p = lector.Pendiente(negocio="GutLyn", titulo="Post", cuerpo="", acciones=[
        lector.Accion("Aprobar y publicar", "claire.aprobar_y_publicar", "publica", False),
        lector.Accion("Regenerar", "claire.regenerar", "cambia_estado", True)])
    monkeypatch.setattr(lector, "pendientes", lambda: ([p], [], []))
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


def test_responde_le_pasa_de_verdad_el_estado_al_contexto(monkeypatch):
    """EL FALLO QUE HIZO FALTA TRES INTENTOS (2026-09-27).

    `responde()` recibía `estado` y `ventas` y NO se los pasaba a `_contexto()`: el reemplazo de esa
    línea nunca se aplicó y yo no lo comprobé. Los tests que tenía miraban que el endpoint pidiera
    el estado y que `_contexto` supiera pintarlo, pero ninguno miraba el ÚNICO punto donde se unen
    las dos mitades. Por eso pasaban con el fallo dentro.

    Se ve preguntándole por la caja: el contexto la tiene y el chat decía que no.

    SE COMPRUEBA SOBRE LA LLAMADA DE VERDAD, no sobre el texto del fuente. La primera version
    buscaba la linea literal `_contexto(pendientes, colas, ...)` y se rompio sola el 28-sep al
    anadir dos argumentos mas: un guardian que hay que reescribir cada vez que cambia una firma
    acaba relajandose hasta no comprobar nada. Aqui se mira lo unico que importa, que es lo que
    llega al modelo.
    """
    import json as _json
    from servicio import chat as m

    visto = {}

    class _R:
        def read(self): return _json.dumps(
            {"content": [{"type": "text", "text": "ok"}],
             "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _falso(req, timeout=0):
        visto["cuerpo"] = _json.loads(req.data)
        return _R()

    monkeypatch.setattr(m.urllib.request, "urlopen", _falso)
    monkeypatch.setattr(m, "CLAVE_ANTHROPIC", "de-mentira")
    m.responde("y la caja?", [], [], [], [],
               estado={"zenvrax": {"negocios": [{"nombre": "Zenvrax", "sub": "consultoria",
                                                 "kpis": [{"k": "Caja", "v": "$1,150"}]}]}},
               ventas={"resumen": {"revenue": 0, "orders": 0}},
               recuerdos="LO QUE EL OPERADOR TE HA PEDIDO RECORDAR: los arcos son de dos",
               hechos=[{"titulo": "post de X aprobado", "resultado": "hecho", "cuando": 1}])
    mandado = visto["cuerpo"]["messages"][-1]["content"]
    for trozo in ("Caja", "$1,150", "VENTAS DE GUTLYN", "los arcos son de dos",
                  "post de X aprobado"):
        assert trozo in mandado, f"el chat se queda ciego: no le llega {trozo}"


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
    assert d["cuentas"], "tiene que salir al menos el buzon del operador"
    assert all(c["configurada"] is False and c["conectada"] is False for c in d["cuentas"])
    # Y los alias NO salen entre lo conectable: un alias no se autoriza, su buzon ya lo esta.
    assert not [c for c in d["cuentas"] if c["negocio"] in api_mod.google.ALIAS]


def test_conectar_una_cuenta_que_no_existe_da_404():
    assert cliente.post("/api/google/conectar?negocio=acme",
                        headers=CABECERA).status_code == 404


def test_un_alias_no_se_puede_conectar_ni_forzandolo():
    """La pantalla ya no ofrece el boton, pero la puerta tambien se cierra por detras: pedir
    permiso para un alias abriria una autorizacion al MISMO buzon y volveria el duplicado."""
    assert "gutlyn" in api_mod.google.ALIAS
    assert cliente.post("/api/google/conectar?negocio=gutlyn",
                        headers=CABECERA).status_code == 404


def test_el_enlace_de_conectar_lleva_el_vale(monkeypatch):
    monkeypatch.setattr(api_mod.google, "enlace_para_autorizar",
                        lambda n, estado="": "https://g/?x=1&state=" + estado)
    d = cliente.post("/api/google/conectar?negocio=zenvrax", headers=CABECERA).json()
    assert d["enlace"].count("state=") == 1, "dos veces state y Google bloquea el acceso"
    vale = d["enlace"].split("state=")[1]
    assert api_mod._VALES[vale][0] == "zenvrax", "el vale tiene que recordar de qué buzón era"


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


# ---------------------------------------------------------------- la agenda que propone

def test_proponer_una_cita_no_la_crea(monkeypatch):
    """La promesa de esta pieza, comprobada en el endpoint y no solo en el modulo: el operador pulsa
    Proponer y en Google todavia no existe nada."""
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {"zenvrax": {}})
    monkeypatch.setattr(api_mod.google, "escribe",
                        lambda *a, **k: pytest.fail("ha creado la cita al proponer"))
    monkeypatch.setattr(api_mod.citas, "propone",
                        lambda *a, **k: {"vale": "v1", "titulo": "X", "avisa_a_invitados": False})
    r = cliente.post("/api/agenda/proponer", headers=CABECERA,
                     json={"titulo": "Llamada", "desde": "2030-01-01T10:00:00"})
    assert r.status_code == 200 and r.json()["vale"] == "v1"


def test_confirmar_con_un_vale_muerto_da_410_y_no_crea(monkeypatch):
    """410 y no 400: la propuesta EXISTIO y ya no esta. El front lo distingue para decir "vuelve a
    pedirla" en vez de "algo ha ido mal"."""
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {"zenvrax": {}})
    monkeypatch.setattr(api_mod.google, "escribe",
                        lambda *a, **k: pytest.fail("ha creado la cita sin vale"))
    r = cliente.post("/api/agenda/confirmar", headers=CABECERA, json={"vale": "inventado"})
    assert r.status_code == 410


def test_sin_permiso_de_escritura_se_dice_lo_que_falta(monkeypatch):
    """El error crudo de Google es un 403 pelado. Lo que hay que leer es que falta abrir el tramo,
    porque si no se busca el fallo en el sitio equivocado."""
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {"zenvrax": {}})
    def sin(_v):
        raise api_mod.google.NoAutorizado("hay que abrir el tramo de calendario")
    monkeypatch.setattr(api_mod.citas, "confirma", sin)
    r = cliente.post("/api/agenda/confirmar", headers=CABECERA, json={"vale": "v"})
    assert r.status_code == 503 and "tramo" in r.json()["detail"]


def test_la_agenda_necesita_una_cuenta_conectada(monkeypatch):
    """Sin cuenta, proponer huecos seria inventarselos."""
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {})
    assert cliente.get("/api/agenda/huecos", headers=CABECERA).status_code == 503


# ---------------------------------------------------------------- lo primero de la mañana

def _hoy_sin_ia(monkeypatch, plan=None, avisos=None):
    monkeypatch.setattr(lector, "plan_del_dia", lambda: (plan or {}, []))
    monkeypatch.setattr(lector, "alertas", lambda: (avisos or [], []))
    monkeypatch.setattr(lector, "negocios", lambda: ([], []))
    monkeypatch.setattr(api_mod.personal, "bandeja",
                        lambda: ({"correos": [], "agenda": [], "cuentas": {}}, []))


def test_la_pantalla_de_hoy_sale_aunque_el_resumen_falle(monkeypatch):
    """EL TEST QUE IMPORTA de esta pantalla. El texto escrito es el adorno; el foco y lo urgente son
    la pieza. Si una caida de la API de Anthropic dejara la pantalla en blanco, lo primero que ve el
    operador por la mañana dependeria de un servicio de fuera."""
    _hoy_sin_ia(monkeypatch, plan={"foco": {"titulo": "Responder a Era Emre"},
                                   "urgentes": [{"titulo": "Landing de XSupport"}]})
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", True)
    def revienta(_c):
        raise RuntimeError("la API no contesta")
    monkeypatch.setattr(api_mod.chat_mod, "resumen_de_la_manana", revienta)
    d = cliente.get("/api/hoy", headers=CABECERA).json()
    assert d["plan"]["foco"]["titulo"] == "Responder a Era Emre"
    assert d["resumen"] is None

    # EL TEXTO SE ESCRIBE POR DETRAS desde el 30-sep (cuesta 3,4s medidos y no puede retrasar la
    # pantalla), asi que el fallo ya no llega en esta respuesta: llega a quien pregunta POR EL
    # RESUMEN. Lo que no cambia es que NO se calla, que es lo que este test defiende.
    import time as _t
    for _ in range(100):
        r = cliente.get("/api/hoy/resumen", headers=CABECERA).json()
        if r["fallos"]:
            break
        _t.sleep(0.02)
    assert r["resumen"] is None
    assert any("resumen" in f for f in r["fallos"]), "y se dice que falta, no se calla"
    assert r["en_camino"] is False, "dice que sigue escribiendose cuando ya fallo"


def test_sin_el_chat_encendido_la_pantalla_no_gasta_nada(monkeypatch):
    """El resumen cuesta dinero. Con el chat apagado no puede colarse por otra puerta."""
    _hoy_sin_ia(monkeypatch, plan={"foco": None, "urgentes": []})
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", False)
    monkeypatch.setattr(api_mod.chat_mod, "resumen_de_la_manana",
                        lambda *a, **k: pytest.fail("ha gastado API con el chat apagado"))
    assert cliente.get("/api/hoy", headers=CABECERA).json()["resumen"] is None


def test_se_puede_pedir_la_pantalla_sin_narrar(monkeypatch):
    """Para recargar tirando del dedo sin volver a pagar."""
    _hoy_sin_ia(monkeypatch)
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", True)
    monkeypatch.setattr(api_mod.chat_mod, "resumen_de_la_manana",
                        lambda *a, **k: pytest.fail("ha narrado con narrar=false"))
    assert cliente.get("/api/hoy?narrar=false", headers=CABECERA).json()["resumen"] is None


def test_el_resumen_ve_mas_de_lo_que_enseña_la_pantalla(monkeypatch):
    """La pantalla enseña el foco y lo urgente, que es lo que se pidio. Pero decidir bien necesita
    ver todo: una cita a las 10 cambia cual es lo primero del dia, y sin saberlo el resumen propone
    algo imposible."""
    monkeypatch.setattr(lector, "plan_del_dia", lambda: (
        {"foco": {"titulo": "Un DM"}, "urgentes": [{"titulo": "Una landing"}],
         "resto": [{"titulo": "Algo menor"}]}, []))
    monkeypatch.setattr(lector, "alertas",
                        lambda: ([{"negocio": "GutLyn+", "texto": "57 signups sin contactar"}], []))
    monkeypatch.setattr(lector, "negocios", lambda: (
        [{"nombre": "Zenvrax IO", "kpis": [{"k": "Caja", "v": "$1.150"}], "pendiente": 82}], []))
    monkeypatch.setattr(api_mod.personal, "bandeja", lambda: (
        {"correos": [{"asunto": "x"}], "agenda": [{"cuando": "2026-10-08T10:00", "titulo": "Con JS"}],
         "cuentas": {}}, []))
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", True)
    visto = {}
    monkeypatch.setattr(api_mod.chat_mod, "resumen_de_la_manana",
                        lambda c, **k: visto.update(c=c) or {"texto": "ok"})
    cliente.get("/api/hoy", headers=CABECERA)
    for tiene_que_estar in ("Un DM", "Una landing", "Algo menor", "57 signups", "Caja", "Con JS",
                            "Correo sin leer"):
        assert tiene_que_estar in visto["c"], f"al resumen le falta {tiene_que_estar}"


def test_una_fuente_caida_no_vacia_la_pantalla(monkeypatch):
    """Si el cockpit no contesta, lo que falta es el plan, no el dia entero."""
    monkeypatch.setattr(lector, "plan_del_dia", lambda: ({}, ["el plan del dia: HTTP 502"]))
    monkeypatch.setattr(lector, "alertas",
                        lambda: ([{"negocio": "GutLyn+", "texto": "57 signups"}], []))
    monkeypatch.setattr(lector, "negocios", lambda: ([], []))
    monkeypatch.setattr(api_mod.personal, "bandeja",
                        lambda: ({"correos": [], "agenda": [], "cuentas": {}}, []))
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", False)
    d = cliente.get("/api/hoy", headers=CABECERA).json()
    assert d["avisos"], "lo que si se pudo leer sigue saliendo"
    assert any("502" in f for f in d["fallos"])


def test_ningun_nombre_local_tapa_un_modulo_importado():
    """PASO DE VERDAD al añadir los avisos: una variable local llamada `avisos` tapaba al modulo
    `avisos` dentro de la pantalla de hoy. No rompia nada porque alli no se usaba el modulo, pero es
    la clase de trampa que revienta en el siguiente cambio y cuesta media hora encontrar.

    Se comprueba el fichero entero: cualquier funcion que reutilice el nombre de un import salta.
    """
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))
    importados = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom):
            importados |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.Import):
            importados |= {(a.asname or a.name).split(".")[0] for a in n.names}

    culpables = []
    for f in ast.walk(arbol):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        locales = {a.arg for a in f.args.args}
        for n in ast.walk(f):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                locales.add(n.id)
        for tapado in locales & importados:
            culpables.append(f"{f.name}() tapa el modulo {tapado}")
    assert not culpables, culpables


# ---------------------------------------------------------------- el chat se acuerda

def test_el_chat_manda_lo_hablado_antes(monkeypatch):
    """Sin esto, cada pregunta partia de cero y un "y eso cuanto es" no tenia a que referirse. Es
    como hablar con alguien a quien se le olvida entre frase y frase."""
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", True)
    monkeypatch.setattr(lector, "pendientes", lambda: ([], [], []))
    monkeypatch.setattr(lector, "estado", lambda: ({}, []))
    monkeypatch.setattr(lector, "ventas_gutlyn", lambda: ({}, []))
    visto = {}
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: visto.update(k) or {"respuesta": "ok"})
    cliente.post("/api/chat", headers=CABECERA, json={
        "texto": "y eso cuanto es",
        "turnos": [{"de": "yo", "texto": "como van las ventas"},
                   {"de": "zeno", "texto": "cero en 30 dias"}]})
    assert len(visto["turnos"]) == 2
    assert visto["turnos"][0]["texto"] == "como van las ventas"


def test_sin_turnos_el_chat_sigue_funcionando(monkeypatch):
    """La primera pregunta de una conversacion no tiene historial, y una version vieja del front
    tampoco lo manda."""
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", True)
    monkeypatch.setattr(lector, "pendientes", lambda: ([], [], []))
    monkeypatch.setattr(lector, "estado", lambda: ({}, []))
    monkeypatch.setattr(lector, "ventas_gutlyn", lambda: ({}, []))
    monkeypatch.setattr(api_mod.chat_mod, "responde", lambda *a, **k: {"respuesta": "ok"})
    assert cliente.post("/api/chat", headers=CABECERA,
                        json={"texto": "hola que tal"}).status_code == 200


def test_ningun_endpoint_usa_un_modelo_declarado_mas_abajo():
    """PASO DE VERDAD en la primera prueba de J4 contra produccion. `accion_confirmar` usaba el
    modelo `Vale`, que se declara doscientas lineas mas abajo. Con `from __future__ import
    annotations` la anotacion es un texto que FastAPI resuelve al registrar la ruta: si la clase no
    existe todavia, NO falla al arrancar. Se traga el modelo, trata el cuerpo como parametro de la
    URL, y el endpoint contesta 422 "field required" con el codigo leyendose perfectamente bien.

    Es de los fallos que no se ven leyendo ni importando, solo llamando. Este test lo convierte en
    algo que se ve leyendo.
    """
    arbol = ast.parse((RAIZ / "servicio" / "api.py").read_text(encoding="utf-8"))
    linea_de = {n.name: n.lineno for n in arbol.body
                if isinstance(n, ast.ClassDef)
                and any(getattr(b, "id", "") == "BaseModel" for b in n.bases)}
    tarde = []
    for f in arbol.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for a in f.args.args + f.args.kwonlyargs:
            nombre = getattr(a.annotation, "id", None)
            if nombre in linea_de and linea_de[nombre] > f.lineno:
                tarde.append(f"{f.name}() usa {nombre}, declarado en la linea {linea_de[nombre]}")
    assert not tarde, tarde


def test_se_dice_que_permiso_le_falta_a_una_cuenta_conectada(monkeypatch):
    """PASO DE VERDAD hoy. Se abrio el tramo de borradores, la cuenta seguia conectada con los
    permisos VIEJOS, y la funcion nueva habria fallado sin explicar por que. Encima el boton de
    reconectar estaba escondido en una linea pequeña al final de la pantalla, asi que no habia
    forma de arreglarlo desde la aplicacion.

    Zeno sabe que permisos pidio y cuales le dieron: no decirlo era guardarse el dato que convierte
    "no funciona" en "reconecta y ya".
    """
    monkeypatch.setenv("ZENO_TRAMO", "agenda,borrador")
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {"zenvrax": {
        "cuenta": "yo@zenvrax.com", "buzon": "yo@zenvrax.com",
        "permisos": ["https://www.googleapis.com/auth/gmail.readonly",
                     "https://www.googleapis.com/auth/calendar.readonly",
                     "https://www.googleapis.com/auth/calendar.events", "openid", "email"]}})
    c = cliente.get("/api/google/cuentas", headers=CABECERA).json()["cuentas"][0]
    assert c["conectada"] is True
    assert c["faltan"] == [api_mod.google.PERMISO_BORRADOR]


def test_una_cuenta_al_dia_no_tiene_nada_que_reconectar(monkeypatch):
    """Y al reves: si avisara siempre, el aviso seria ruido y se dejaria de mirar."""
    monkeypatch.setenv("ZENO_TRAMO", "leer")
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {"zenvrax": {
        "cuenta": "yo@zenvrax.com", "permisos": list(api_mod.google.PERMISOS_LEER)}})
    c = cliente.get("/api/google/cuentas", headers=CABECERA).json()["cuentas"][0]
    assert c["faltan"] == []


def test_una_cuenta_sin_conectar_no_sale_como_falta_de_permisos(monkeypatch):
    """Son dos cosas distintas y se arreglan igual, pero el mensaje no puede confundirlas: "sin
    conectar" y "le falta un permiso" llevan a mirar sitios diferentes."""
    monkeypatch.setenv("ZENO_TRAMO", "agenda,borrador")
    monkeypatch.setattr(api_mod.google, "conectadas", lambda: {})
    c = cliente.get("/api/google/cuentas", headers=CABECERA).json()["cuentas"][0]
    assert c["conectada"] is False and c["faltan"] == []


# ---------------------------------------------------------------- lo que Zeno recuerda

@pytest.fixture()
def _memoria_limpia(tmp_path, monkeypatch):
    """La memoria real escribe en /datos, que aquí no existe. Sin esto los tests pasarían por el
    camino silencioso del `except OSError` y no comprobarían nada."""
    monkeypatch.setattr(api_mod.memoria, "FICHERO", tmp_path / "memoria.jsonl")
    monkeypatch.setattr(api_mod.memoria, "HILO", tmp_path / "conversacion.jsonl")
    return api_mod.memoria


@pytest.fixture()
def _chat_encendido(monkeypatch):
    monkeypatch.setattr(api_mod, "CHAT_ACTIVO", True)
    monkeypatch.setattr(lector, "pendientes", lambda: ([], {}, []))
    monkeypatch.setattr(lector, "estado", lambda: ({}, []))
    monkeypatch.setattr(lector, "ventas_gutlyn", lambda: ({}, []))


def test_pedirle_que_recuerde_algo_no_gasta_api(monkeypatch, _memoria_limpia, _chat_encendido):
    """EL PUNTO DE TODO ESTO. Pasar "recuerda que los arcos son de dos" por Haiku costaría dinero
    para que parafrasee una orden que ya está clara, y con el riesgo de que guarde SU versión en
    vez de las palabras del operador. Se reconoce con reglas y se guarda tal cual."""
    llamadas = []
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: llamadas.append(1) or {"respuesta": "x"})
    r = cliente.post("/api/chat", json={"texto": "recuerda que los arcos son de dos mensajes"},
                     headers=CABECERA)
    assert r.status_code == 200
    assert llamadas == [], "pasó por el modelo un apunte que no lo necesita"
    assert r.json()["coste_usd"] == 0.0
    assert [a["texto"] for a in _memoria_limpia.apuntes()] == ["Los arcos son de dos mensajes"]


def test_una_pregunta_de_verdad_si_pasa_por_el_modelo(monkeypatch, _memoria_limpia,
                                                      _chat_encendido):
    """El guardián de arriba, con el fallo dentro: si el reconocedor se pasara de listo y se
    tragara las preguntas normales, el chat dejaría de contestar y diría apuntado a todo."""
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: {"respuesta": "cero ventas", "coste_usd": 0.002})
    r = cliente.post("/api/chat", json={"texto": "cómo van las ventas"}, headers=CABECERA)
    assert r.json()["respuesta"] == "cero ventas"
    assert _memoria_limpia.apuntes() == [], "una pregunta normal no es un apunte"


def test_la_conversacion_se_guarda_para_manana(monkeypatch, _memoria_limpia, _chat_encendido):
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: {"respuesta": "cero ventas", "coste_usd": 0.002})
    cliente.post("/api/chat", json={"texto": "cómo van las ventas"}, headers=CABECERA)
    assert [(t["de"], t["texto"]) for t in _memoria_limpia.hilo()] == [
        ("tu", "cómo van las ventas"), ("zeno", "cero ventas")]


def test_si_la_respuesta_falla_no_queda_media_conversacion(monkeypatch, _memoria_limpia,
                                                           _chat_encendido):
    """Al volver mañana, un turno tuyo sin contestar se leería como algo que quedó pendiente, y el
    modelo arrancaría respondiendo a una pregunta que nunca llegó a contestarse."""
    def _revienta(*a, **k):
        raise api_mod.chat_mod.SinClaveDeIA("no hay clave")

    monkeypatch.setattr(api_mod.chat_mod, "responde", _revienta)
    assert cliente.post("/api/chat", json={"texto": "y las ventas"},
                        headers=CABECERA).status_code == 503
    assert _memoria_limpia.hilo() == []


def test_al_abrir_la_aplicacion_se_retoma_lo_hablado(monkeypatch, _memoria_limpia,
                                                     _chat_encendido):
    """Sin turnos del front (acaba de abrir la aplicación) el chat parte de lo guardado. Este es
    literalmente el "que la conversación siga donde la dejaste" que se pidió."""
    _memoria_limpia.guarda_turno("tu", "cuántos DMs quedan")
    _memoria_limpia.guarda_turno("zeno", "quince")
    visto = {}
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: visto.update(k) or {"respuesta": "ok", "coste_usd": 0})
    cliente.post("/api/chat", json={"texto": "y mañana"}, headers=CABECERA)
    assert [t["texto"] for t in visto["turnos"]] == ["cuántos DMs quedan", "quince"]


def test_los_turnos_de_la_pantalla_mandan_sobre_los_guardados(monkeypatch, _memoria_limpia,
                                                              _chat_encendido):
    """Lo que el operador está viendo es la verdad. Si lo guardado pisara la pantalla, el chat
    contestaría a una conversación distinta de la que él tiene delante."""
    _memoria_limpia.guarda_turno("tu", "de ayer")
    visto = {}
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: visto.update(k) or {"respuesta": "ok", "coste_usd": 0})
    cliente.post("/api/chat", json={"texto": "y ahora",
                                    "turnos": [{"de": "tu", "texto": "de la pantalla"}]},
                 headers=CABECERA)
    assert [t["texto"] for t in visto["turnos"]] == ["de la pantalla"]


def test_el_chat_recibe_lo_recordado_y_el_diario(monkeypatch, _memoria_limpia, _chat_encendido):
    """El diario existía desde J4 y el chat no lo veía: preguntarle qué he aprobado hoy era
    preguntarle a alguien que no estaba delante."""
    monkeypatch.setattr(api_mod.diario, "lee", lambda n=40: [{"titulo": "post de X"}])
    _memoria_limpia.apunta("los arcos son de dos")
    visto = {}
    monkeypatch.setattr(api_mod.chat_mod, "responde",
                        lambda *a, **k: visto.update(k) or {"respuesta": "ok", "coste_usd": 0})
    cliente.post("/api/chat", json={"texto": "qué he hecho hoy"}, headers=CABECERA)
    assert "los arcos son de dos" in visto["recuerdos"]
    assert visto["hechos"] == [{"titulo": "post de X"}]


def test_la_memoria_se_puede_mirar_y_borrar(_memoria_limpia):
    """Esta pantalla es la condición para que la memoria exista: una que no se puede corregir
    acaba repitiendo como cierto algo que caducó hace semanas."""
    r = cliente.post("/api/memoria", json={"texto": "GutLyn es mía"}, headers=CABECERA)
    ident = r.json()["apunte"]["id"]
    assert [a["texto"] for a in cliente.get("/api/memoria", headers=CABECERA).json()["apuntes"]] \
        == ["GutLyn es mía"]
    assert cliente.delete("/api/memoria/" + ident, headers=CABECERA).status_code == 200
    assert cliente.get("/api/memoria", headers=CABECERA).json()["apuntes"] == []


def test_borrar_la_conversacion_no_borra_los_apuntes(_memoria_limpia):
    """Si empezar de cero se llevara por delante lo que pidió recordar, nadie volvería a
    pulsarlo, y el hilo viejo acabaría ensuciando todas las respuestas."""
    cliente.post("/api/memoria", json={"texto": "GutLyn es mía"}, headers=CABECERA)
    _memoria_limpia.guarda_turno("tu", "hola")
    assert cliente.delete("/api/hilo", headers=CABECERA).status_code == 200
    assert cliente.get("/api/hilo", headers=CABECERA).json()["turnos"] == []
    assert len(cliente.get("/api/memoria", headers=CABECERA).json()["apuntes"]) == 1


def test_un_apunte_vacio_no_se_guarda(_memoria_limpia):
    assert cliente.post("/api/memoria", json={"texto": "  "}, headers=CABECERA).status_code == 422
    assert _memoria_limpia.apuntes() == []


def test_la_memoria_no_se_mira_sin_sesion(monkeypatch, _memoria_limpia):
    """Lo que el operador pide recordar son sus decisiones y sus datos: no es menos privado que
    el correo."""
    def _no(t, ahora=None):
        raise sesion.NoAutenticado("no")

    monkeypatch.setattr(sesion, "quien_es", _no)
    for metodo, ruta in (("get", "/api/memoria"), ("delete", "/api/memoria/x"),
                         ("get", "/api/hilo"), ("delete", "/api/hilo")):
        assert getattr(cliente, metodo)(ruta).status_code == 401, ruta
    assert cliente.post("/api/memoria", json={"texto": "x"}).status_code == 401
