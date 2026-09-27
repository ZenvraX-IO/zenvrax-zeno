# -*- coding: utf-8 -*-
"""El correo y la agenda del operador: dos cuentas separadas, solo lectura, y nada guardado.

EL CASO. Esta es la fase que toca **datos personales**, y por eso va la última: hasta aquí, lo peor
que podía pasar era publicar un post antes de tiempo. Aquí se lee el correo de dos empresas.

Las dos cuentas (`ghidalgo@zenvrax.com` y `ghidalgo@gutlyn.com`) ya estaban separadas en Google
antes de Zeno, y esa separación es la que sostiene la frontera entre los dos negocios. Si el código
las mezclara, la frontera dejaría de existir sin que nadie tocara una regla.

Lo que estos tests protegen son las cuatro formas de romperlo en silencio:

1. Que se pida el permiso de ENVIAR cuando solo toca leer.
2. Que una cuenta caída o sin conectar se trague la otra, o peor, que se calle.
3. Que los correos acaben guardados en algún sitio.
4. Que Zeno escriba en Google (cualquier método que no sea GET).

Puros: sin red y sin tocar Google.
"""
import ast
import sys
import urllib.parse
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import google, personal        # noqa: E402


@pytest.fixture(autouse=True)
def _tramo_de_lectura(monkeypatch):
    monkeypatch.setenv("ZENO_TRAMO", "leer")
    yield


# ---------------------------------------------------------------- los permisos van por tramos

def test_de_serie_solo_se_pide_leer():
    """El tramo por defecto no puede incluir enviar. Un permiso de envío mal puesto significa que
    alguien puede escribir a los clientes del operador en su nombre."""
    p = google.permisos()
    assert "https://www.googleapis.com/auth/gmail.readonly" in p
    assert "https://www.googleapis.com/auth/calendar.readonly" in p
    for peligroso in google.PERMISOS_ESCRIBIR:
        assert peligroso not in p, f"de serie se esta pidiendo {peligroso}"
    assert google.PERMISO_BORRADOR not in p, "ni siquiera el de borradores va de serie"


def test_los_tramos_se_abren_de_uno_en_uno(monkeypatch):
    monkeypatch.setenv("ZENO_TRAMO", "borrador")
    p = google.permisos()
    assert google.PERMISO_BORRADOR in p, "el tramo de borradores tiene que añadirlo"
    for peligroso in google.PERMISOS_ESCRIBIR:
        assert peligroso not in p, "el de borradores NO abre el de enviar"

    monkeypatch.setenv("ZENO_TRAMO", "escribir")
    assert all(x in google.permisos() for x in google.PERMISOS_ESCRIBIR)


def test_abrir_la_agenda_no_abre_el_envio_de_correo(monkeypatch):
    """EL TRAMO QUE IMPORTA. El operador aprobo el 2026-09-27 que Zeno proponga citas, y nada mas.
    Mientras "escribir" era un solo tramo, abrir la agenda habria pedido tambien `gmail.send`, o
    sea permiso para escribir a sus clientes en su nombre, de rebote y sin que nadie lo decidiera.

    Son dos cosas distintas y por eso son dos tramos: una cita mal puesta se borra, un correo
    enviado no se recoge.
    """
    monkeypatch.setenv("ZENO_TRAMO", "agenda")
    p = google.permisos()
    assert google.PERMISO_AGENDA in p, "el tramo de agenda tiene que abrir calendar.events"
    assert google.PERMISO_ENVIAR not in p, "y NO puede abrir gmail.send"
    assert google.PERMISO_BORRADOR not in p, "ni los borradores, que son otro tramo"


def test_un_tramo_que_no_existe_no_abre_nada_de_mas(monkeypatch):
    """Una errata en el `.env` no puede acabar concediendo mas de lo que dice la palabra."""
    monkeypatch.setenv("ZENO_TRAMO", "escrbir")
    assert google.permisos() == google.PERMISOS_LEER


def test_enviar_y_mover_citas_van_juntos_y_aparte():
    """Son los dos que salen al mundo. Se declaran en su propia lista para que se vea de un vistazo
    qué es lo peligroso, en vez de estar mezclados con los de leer."""
    assert set(google.PERMISOS_ESCRIBIR) == {
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.events"}


# ---------------------------------------------------------------- las dos cuentas no se mezclan

def test_lo_que_se_conecta_y_lo_que_solo_etiqueta_estan_separados():
    """MEDIDO EL 2026-09-27: `ghidalgo@gutlyn.com` es un ALIAS del mismo buzon, no otra cuenta.

    Mientras estuvo en CUENTAS, la pantalla ofrecia un boton Conectar que no podia hacer nada, y
    cuando no estaba autorizado avisaba en rojo de que faltaba correo cuando no faltaba ninguno.
    El operador: *"no tiene mucho sentido ponerla de GutLyn para conectar"*.

    CUENTAS son los buzones que se AUTORIZAN. ALIAS son direcciones que solo sirven para decir de
    que negocio es cada correo. El dia que GutLyn tenga cuenta propia, su linea se mueve de una a
    otra y el boton vuelve solo.
    """
    assert google.CUENTAS == {"zenvrax": "ghidalgo@zenvrax.com"}
    assert google.ALIAS["gutlyn"] == "ghidalgo@gutlyn.com"
    assert "gutlyn" not in google.CUENTAS, "un alias no se conecta: no hay nada que autorizar"
    assert google.direcciones()["zenvrax"] == "ghidalgo@zenvrax.com"
    assert set(google.direcciones()) == set(google.CUENTAS) | set(google.ALIAS)


def test_olvidar_una_cuenta_no_toca_la_otra(monkeypatch, tmp_path):
    """Es toda la gracia de tener dos autorizaciones: revocar GutLyn no puede dejar a Zenvrax
    fuera."""
    monkeypatch.setattr(google, "COFRE", tmp_path / "c")
    monkeypatch.setattr(google, "CLAVE_COFRE", "x" * 32)
    google._guarda_cofre({"zenvrax": {"refresh": "a", "cuenta": "z"},
                          "gutlyn": {"refresh": "b", "cuenta": "g"}})
    google.olvida("gutlyn")
    quedan = google.conectadas()
    assert "zenvrax" in quedan and "gutlyn" not in quedan


def test_un_buzon_sin_conectar_se_dice(monkeypatch):
    """EL TEST QUE IMPORTA. Si un buzon no esta conectado y Zeno enseña el resto sin avisar, el
    operador lee "tengo poco correo" cuando la verdad es "falta un buzon entero"."""
    monkeypatch.setattr(google, "CUENTAS", {"zenvrax": "a@zenvrax.com", "otra": "b@otra.com"})
    monkeypatch.setattr(google, "conectadas", lambda: {"zenvrax": {"buzon": "a@zenvrax.com"}})
    monkeypatch.setattr(personal, "correos", lambda n, **k: [{"asunto": "uno", "negocio": n}])
    monkeypatch.setattr(personal, "agenda", lambda n, **k: [])
    datos, fallos = personal.bandeja()
    assert len(datos["correos"]) == 1
    assert any("b@otra.com" in f for f in fallos), (
        "el buzon que falta tiene que aparecer en los fallos, no desaparecer")


def test_un_alias_no_cuenta_como_buzon_que_falta(monkeypatch):
    """Y AL REVES, que es lo que pasaba en pantalla: el alias salia como "sin conectar todavia" en
    rojo, o sea avisando de que faltaba correo. No faltaba: su buzon ya estaba leido."""
    monkeypatch.setattr(google, "conectadas", lambda: {"zenvrax": {"buzon": "ghidalgo@zenvrax.com"}})
    monkeypatch.setattr(personal, "correos", lambda n, **k: [{"asunto": "uno", "negocio": n}])
    monkeypatch.setattr(personal, "agenda", lambda n, **k: [])
    datos, fallos = personal.bandeja()
    assert fallos == [], f"un alias no falta por conectar: {fallos}"
    assert "gutlyn" in datos["buzones"][0]["negocios"], (
        "pero si tiene que viajar con el buzon, que es lo que etiqueta sus correos")


def test_un_fallo_de_una_cuenta_no_borra_lo_de_la_otra(monkeypatch):
    monkeypatch.setattr(google, "conectadas", lambda: {"zenvrax": {}, "gutlyn": {}})

    def correos(negocio, **k):
        if negocio == "gutlyn":
            raise google.NoAutorizado("permiso retirado")
        return [{"asunto": "de zenvrax", "negocio": negocio}]

    monkeypatch.setattr(personal, "correos", correos)
    monkeypatch.setattr(personal, "agenda", lambda n, **k: [])
    datos, fallos = personal.bandeja()
    assert len(datos["correos"]) == 1 and datos["correos"][0]["negocio"] == "zenvrax"
    assert any("permiso retirado" in f for f in fallos)


# ---------------------------------------------------------------- ni guarda ni escribe

def test_los_correos_no_se_guardan_en_ningun_sitio():
    """Zeno guarda UNA cosa, el permiso de Google, y se guarda porque si no hay que reautorizar en
    cada reinicio. Los correos se leen y se olvidan: una copia sería el tercer sitio con los datos
    personales del operador."""
    arbol = ast.parse((RAIZ / "servicio" / "personal.py").read_text(encoding="utf-8"))
    escrituras = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr in ("write_text", "write_bytes", "open", "dump", "execute")]
    assert not escrituras, f"personal.py escribe en algún sitio: {[n.func.attr for n in escrituras]}"


def test_solo_hay_una_puerta_de_escritura_y_se_sabe_quien_la_usa():
    """Hasta el 2026-09-27 Zeno no escribia en Google, y el guardian decia que `pide` era la unica
    forma de hablar con el. Al aparecer la agenda que crea citas eso dejo de ser verdad, y este
    test salto: lo que hace es lo que tiene que hacer.

    La verdad nueva es mas estrecha: hay UNA funcion que escribe, `google.escribe`, y solo la llama
    `citas.py`, y alli solo desde `confirma()`. El dia que alguien la llame desde otro sitio, lo
    que se escapa es un correo o una cita que otra persona ya ha visto, y eso no se deshace.
    """
    servicio = RAIZ / "servicio"
    culpables = []
    for f in servicio.glob("*.py"):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "escribe"
                    and getattr(n.func.value, "id", "") == "google"):
                culpables.append(f.name)
    assert sorted(set(culpables)) == ["citas.py", "correo.py"], (
        f"alguien mas escribe en Google: {sorted(set(culpables))}")


def test_escribir_en_google_solo_pasa_por_confirmar():
    """Lo que importa no es el nombre exacto de la funcion, es la FORMA: quien escribe es siempre
    quien consume un vale, nunca quien lo reparte. Si una funcion `propone` o `prepara` escribiera,
    la cita o el borrador existirian antes de que el operador los mirara, y los dos tiempos no
    servirian de nada."""
    for fichero, permitidas in (("citas.py", ("confirma",)), ("correo.py", ("guarda",))):
        _solo_escriben(fichero, permitidas)


def _solo_escriben(fichero, permitidas):
    arbol = ast.parse((RAIZ / "servicio" / fichero).read_text(encoding="utf-8"))
    dentro_de = []
    for f in ast.walk(arbol):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(f):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "escribe"):
                dentro_de.append(f.name)
    # Solo las funciones que CONFIRMAN. Lo que importa no es el nombre exacto sino la forma: una
    # funcion `propone*` nunca puede escribir, porque entonces la cita existiria antes de que el
    # operador la mirara y los dos tiempos no servirian de nada.
    assert dentro_de, f"nadie escribe en Google desde {fichero}: falta la pieza que confirma"
    for donde in dentro_de:
        assert donde.startswith(permitidas), f"{fichero}: se escribe desde {donde}"
    assert not [x for x in dentro_de if x.startswith(("propone", "prepara"))]


def test_personal_sigue_sin_poder_escribir():
    """El correo se lee y no se toca. Esta parte no ha cambiado y no puede cambiar de rebote."""
    arbol = ast.parse((RAIZ / "servicio" / "personal.py").read_text(encoding="utf-8"))
    llamadas = [n.func.attr for n in ast.walk(arbol) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.value.__class__.__name__ == "Name"
                and getattr(n.func.value, "id", "") == "google"]
    assert set(llamadas) <= {"pide", "conectadas", "direcciones"}, (
        f"personal.py llama a google con algo que no es leer: {set(llamadas)}")


def test_sin_clave_del_cofre_no_se_guarda_nada(monkeypatch):
    """Sin la clave, guardar un token dejaría credenciales en claro en el disco."""
    monkeypatch.setattr(google, "CLAVE_COFRE", "")
    with pytest.raises(google.SinConfigurar):
        google._guarda_cofre({"zenvrax": {"refresh": "secreto"}})


def test_el_permiso_guardado_no_se_puede_leer_a_ojo(monkeypatch, tmp_path):
    """Si el token quedara en claro, aparecería tal cual en un backup o en un volcado del disco."""
    cofre = tmp_path / "c"
    monkeypatch.setattr(google, "COFRE", cofre)
    monkeypatch.setattr(google, "CLAVE_COFRE", "una clave larga de verdad")
    google._guarda_cofre({"zenvrax": {"refresh": "TOKEN-SECRETO-123"}})
    assert "TOKEN-SECRETO-123" not in cofre.read_bytes().decode("utf-8", "replace")
    assert google._lee_cofre()["zenvrax"]["refresh"] == "TOKEN-SECRETO-123"


def test_conectadas_nunca_devuelve_los_tokens(monkeypatch, tmp_path):
    """Lo consume el front. Un token en una respuesta HTTP acaba en el historial del navegador."""
    monkeypatch.setattr(google, "COFRE", tmp_path / "c")
    monkeypatch.setattr(google, "CLAVE_COFRE", "x" * 32)
    google._guarda_cofre({"zenvrax": {"refresh": "SECRETO", "acceso": "TAMBIEN",
                                      "cuenta": "z@z.com", "permisos": "a b"}})
    fuera = google.conectadas()["zenvrax"]
    assert "SECRETO" not in str(fuera) and "TAMBIEN" not in str(fuera)
    assert fuera["cuenta"] == "z@z.com"


def test_cada_cuenta_puede_tener_su_propio_cliente_oauth(monkeypatch):
    """MEDIDO EL 2026-09-27: los dos dominios usan Google Workspace y son dominios distintos.

    Una aplicación "interna" solo vale dentro de su organización, y una "externa" en modo prueba
    caduca el permiso **cada 7 días** con los permisos de Gmail, que Google considera restringidos.
    Con un cliente por cuenta, cada una puede ser interna en la suya: sin verificación y sin
    reautorizar cada semana.

    Si al final las dos están en la misma organización, basta con poner el mismo par en las dos.
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID_ZENVRAX", "id-z")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET_ZENVRAX", "sec-z")
    monkeypatch.setenv("GOOGLE_CLIENT_ID_GUTLYN", "id-g")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET_GUTLYN", "sec-g")
    assert google._cliente("zenvrax") == ("id-z", "sec-z")
    assert google._cliente("gutlyn") == ("id-g", "sec-g")


def test_si_solo_hay_un_cliente_comun_sirve_para_las_dos(monkeypatch):
    """El caso en que las dos cuentas están en la misma organización de Workspace."""
    for v in ("GOOGLE_CLIENT_ID_ZENVRAX", "GOOGLE_CLIENT_ID_GUTLYN",
              "GOOGLE_CLIENT_SECRET_ZENVRAX", "GOOGLE_CLIENT_SECRET_GUTLYN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "uno")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "otro")
    assert google._cliente("zenvrax") == ("uno", "otro") == google._cliente("gutlyn")


def test_sin_cliente_configurado_se_dice_cual_falta(monkeypatch):
    """Un mensaje genérico obligaría a adivinar cuál de las dos cuentas está sin configurar."""
    for v in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID_ZENVRAX"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(google.SinConfigurar) as e:
        google.enlace_para_autorizar("zenvrax")
    assert "ZENVRAX" in str(e.value)


def test_el_enlace_acota_el_dominio_y_fuerza_el_selector(monkeypatch):
    """MEDIDO CON EL OPERADOR EL 2026-09-27: al pulsar Conectar, Google cogia la cuenta personal que
    ya tenia abierta en el navegador y, al ser la aplicacion INTERNA de la organizacion, respondia
    con el acceso bloqueado.

    Dos parametros lo arreglan y los dos hacen falta:
      · `hd` acota el selector al dominio de esa cuenta, asi que una de gmail.com ni aparece.
      · `select_account` obliga a que el selector SALGA, en vez de reutilizar la sesion abierta.
    `login_hint` solo sugiere, y por eso no bastaba.
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    enlace = google.enlace_para_autorizar("zenvrax")
    trozos = urllib.parse.parse_qs(urllib.parse.urlparse(enlace).query)
    assert trozos["hd"] == ["zenvrax.com"], "sin hd, el selector ofrece cuentas de fuera"
    assert "select_account" in trozos["prompt"][0], "sin esto reutiliza la sesion abierta"
    assert "consent" in trozos["prompt"][0], "sin consent Google no entrega el token de refresco"

    # Cada buzon acota a SU dominio, no a uno fijo: se comprueba con uno inventado para que el
    # test siga valiendo el dia que haya un segundo buzon de verdad.
    monkeypatch.setitem(google.CUENTAS, "otra", "alguien@otracasa.com")
    otros = urllib.parse.parse_qs(
        urllib.parse.urlparse(google.enlace_para_autorizar("otra")).query)
    assert otros["hd"] == ["otracasa.com"]


def test_el_dominio_sale_de_la_cuenta_y_no_esta_escrito_a_mano():
    """Si el dominio fuera una constante, añadir una tercera cuenta la mandaria al dominio de otra."""
    assert google._dominio("a@b.com") == "b.com"
    assert google._dominio("raro") == "", "sin arroba no hay dominio que acotar, y no se inventa"


def test_el_enlace_no_repite_ningun_parametro(monkeypatch):
    """PASO DE VERDAD el 2026-09-27, en la primera autorizacion real: el enlace llevaba `state` dos
    veces, uno puesto aqui y otro pegado al final por el servicio, y Google contesto "Acceso
    bloqueado: OAuth 2 parameters can only have a single value: state".

    Se comprueba TODA la direccion y no solo `state`: el mismo error se puede repetir manana con
    `prompt` o con `scope`, y el mensaje de Google es igual de opaco.
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    enlace = google.enlace_para_autorizar("zenvrax", "vale-de-un-solo-uso")
    trozos = urllib.parse.parse_qs(urllib.parse.urlparse(enlace).query)
    repetidos = {k: v for k, v in trozos.items() if len(v) > 1}
    assert not repetidos, f"Google rechaza los parametros repetidos: {repetidos}"
    assert trozos["state"] == ["vale-de-un-solo-uso"], "el vale tiene que ser EL state, no otro mas"


# ------------------------------------------------- un buzon con dos nombres se lee UNA vez

def test_dos_autorizaciones_al_mismo_buzon_no_duplican_el_correo(monkeypatch):
    """PASO DE VERDAD el 2026-09-27. Se dio por hecho que `ghidalgo@zenvrax.com` y
    `ghidalgo@gutlyn.com` eran dos cuentas de Google, porque son dos dominios y los dos tienen
    Workspace. Preguntandoselo a Google: mismo buzon, 498 mensajes, mismo historyId. El segundo es
    un ALIAS.

    Resultado en pantalla: cada correo aparecia dos veces, uno etiquetado ZENVRAX y otro GUTLYN. Y
    lo peor no era el duplicado, era que la etiqueta mentia: decia de que permiso venia, no de que
    negocio era.
    """
    monkeypatch.setattr(google, "conectadas", lambda: {
        "zenvrax": {"cuenta": "ghidalgo@zenvrax.com", "buzon": "ghidalgo@zenvrax.com"},
        "gutlyn": {"cuenta": "ghidalgo@gutlyn.com", "buzon": "ghidalgo@zenvrax.com"}})
    leidos = []
    monkeypatch.setattr(personal, "correos",
                        lambda n, **k: leidos.append(n) or [{"asunto": "uno", "negocio": n}])
    monkeypatch.setattr(personal, "agenda", lambda n, **k: [])
    datos, fallos = personal.bandeja()
    assert len(leidos) == 1, f"el mismo buzon se ha leido {len(leidos)} veces"
    assert len(datos["correos"]) == 1, "el correo sale duplicado"
    assert not fallos
    assert "gutlyn" in datos["buzones"][0]["alias_de"], "se dice que gutlyn es un alias"


def test_dos_buzones_de_verdad_se_siguen_leyendo_los_dos(monkeypatch):
    """El arreglo de arriba no puede colapsar dos buzones que SI son distintos: eso escondería la
    mitad del correo y nadie lo notaria, que es peor que el duplicado."""
    monkeypatch.setattr(google, "conectadas", lambda: {
        "zenvrax": {"buzon": "a@zenvrax.com"}, "gutlyn": {"buzon": "b@gutlyn.com"}})
    leidos = []
    monkeypatch.setattr(personal, "correos",
                        lambda n, **k: leidos.append(n) or [{"asunto": n, "negocio": n}])
    monkeypatch.setattr(personal, "agenda", lambda n, **k: [])
    datos, _ = personal.bandeja()
    assert sorted(leidos) == ["gutlyn", "zenvrax"]
    assert len(datos["correos"]) == 2


def test_el_negocio_sale_de_a_quien_iba_el_correo():
    """Con un alias, leer con el permiso de Zenvrax no dice nada del negocio. Lo que lo dice es la
    direccion a la que llego, y por eso se piden las cabeceras Delivered-To, To y Cc."""
    negocios = ["zenvrax", "gutlyn"]
    assert personal._de_quien_es("ghidalgo@gutlyn.com", negocios) == "gutlyn"
    assert personal._de_quien_es("Gustavo <GHIDALGO@GUTLYN.COM>", negocios) == "gutlyn"
    # Otra direccion del mismo dominio tambien es del negocio: no se compara la direccion entera.
    assert personal._de_quien_es("hola@gutlyn.com", negocios) == "gutlyn"
    assert personal._de_quien_es("ghidalgo@zenvrax.com", negocios) == "zenvrax"
    # Lo que no va a ninguno de los alias cae en el dueño del buzon, no se pierde ni se inventa.
    assert personal._de_quien_es("cualquiera@otra.com", negocios) == "zenvrax"
    assert personal._de_quien_es("", negocios) == "zenvrax"


def test_un_dominio_que_es_sufijo_de_otro_no_se_confunde():
    """`gutlyn.com` y `migutlyn.com` comparten final. Comparar el texto suelto marcaria el segundo
    como GutLyn; por eso se busca con la arroba delante."""
    assert personal._de_quien_es("alguien@migutlyn.com", ["zenvrax", "gutlyn"]) == "zenvrax"


def test_el_enlace_de_gmail_no_mete_el_correo_en_el_tramo_de_la_cuenta():
    """PASO DE VERDAD: el enlace era `/mail/u/<correo>/`, y ese tramo espera el NUMERO de cuenta
    (0, 1, 2). Con un correo, Gmail contesta "Temporary Error (404)" y el correo no se abre."""
    enlace = personal._abre_correo("ghidalgo@zenvrax.com", "abc123")
    assert "/mail/u/ghidalgo" not in enlace, "el correo no puede ir en el tramo /u/"
    assert "authuser=" in enlace, "sin authuser abre en la sesion que haya delante, que es otra"
    assert enlace.endswith("#inbox/abc123")


def test_una_marca_retirada_no_vuelve_por_recibir_correo():
    """La direccion de Zondra sigue recibiendo (2 de 14 correos en 30 dias) y al medirlo la añadi
    como tercer negocio por mi cuenta. El operador: *"es solo Zenvrax y Gutlyn, Zondra esta
    obsoleto"*.

    La leccion es sobre quien decide: que exista un dato no significa que exista el negocio. Una
    marca retirada no vuelve a la pantalla porque la bandeja la mencione.
    """
    assert "zondra" not in google.ALIAS
    assert set(google.ALIAS) == {"gutlyn"}
    negocios = ["zenvrax", "gutlyn"]
    # Y su correo no se pierde: cae en el dueño del buzon, que es lo que es.
    assert personal._de_quien_es("ghidalgo@zb-zondra.com", negocios) == "zenvrax"
    assert personal._de_quien_es("ghidalgo@gutlyn.com", negocios) == "gutlyn"


def test_la_agenda_no_mira_solo_tres_dias():
    """La pantalla decia "nada en los proximos dias" teniendo una cita dentro del mes. Con una
    agenda poco cargada, tres dias enseñan vacio casi siempre y el apartado parece roto."""
    assert personal.DIAS_DE_AGENDA >= 14


def test_se_pueden_abrir_dos_tramos_a_la_vez(monkeypatch):
    """Antes el tramo era uno solo y se pisaban: al abrir la agenda habria que elegir entre mover
    citas o dejar borradores, cuando son cosas distintas que no tienen por que excluirse."""
    monkeypatch.setenv("ZENO_TRAMO", "agenda,borrador")
    p = google.permisos()
    assert google.PERMISO_AGENDA in p and google.PERMISO_BORRADOR in p
    assert google.PERMISO_ENVIAR not in p, "y seguir sin poder enviar correo"
    assert len(p) == len(set(p)), "sin repetidos"


def test_un_tramo_desconocido_en_la_lista_no_abre_nada_de_mas(monkeypatch):
    """Una errata en el `.env` no puede concedes mas de lo que dicen las palabras escritas."""
    monkeypatch.setenv("ZENO_TRAMO", "agenda,escrbir,borradr")
    p = google.permisos()
    assert google.PERMISO_AGENDA in p
    assert google.PERMISO_ENVIAR not in p and google.PERMISO_BORRADOR not in p


def test_el_permiso_corto_y_el_largo_son_el_mismo(monkeypatch):
    """PASO DE VERDAD al comprobarlo en produccion. Zeno pide `email` y Google concede
    `.../userinfo.email`. Comparando las cadenas tal cual, `email` figuraba como que FALTABA para
    siempre, asi que el aviso de "reconecta" se habria quedado puesto sin que reconectar lo quitara
    nunca. Un aviso que no se puede apagar deja de mirarse, y con el se deja de mirar el que si
    importaba.
    """
    monkeypatch.setenv("ZENO_TRAMO", "leer")
    concedidos = ["https://www.googleapis.com/auth/gmail.readonly",
                  "https://www.googleapis.com/auth/calendar.readonly",
                  "https://www.googleapis.com/auth/userinfo.email", "openid"]
    assert google.faltan(concedidos) == [], google.faltan(concedidos)


def test_lo_que_falta_de_verdad_sigue_saliendo(monkeypatch):
    """Y el arreglo no puede tragarse lo que si falta: entonces el aviso no serviria para nada."""
    monkeypatch.setenv("ZENO_TRAMO", "agenda,borrador")
    concedidos = ["https://www.googleapis.com/auth/gmail.readonly",
                  "https://www.googleapis.com/auth/calendar.readonly",
                  "https://www.googleapis.com/auth/userinfo.email", "openid"]
    f = google.faltan(concedidos)
    assert google.PERMISO_BORRADOR in f and google.PERMISO_AGENDA in f
    assert "email" not in f
