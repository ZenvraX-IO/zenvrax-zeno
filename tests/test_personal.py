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


def test_enviar_y_mover_citas_van_juntos_y_aparte():
    """Son los dos que salen al mundo. Se declaran en su propia lista para que se vea de un vistazo
    qué es lo peligroso, en vez de estar mezclados con los de leer."""
    assert set(google.PERMISOS_ESCRIBIR) == {
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.events"}


# ---------------------------------------------------------------- las dos cuentas no se mezclan

def test_hay_dos_cuentas_y_cada_una_es_de_su_negocio():
    assert google.CUENTAS["zenvrax"] == "ghidalgo@zenvrax.com"
    assert google.CUENTAS["gutlyn"] == "ghidalgo@gutlyn.com"


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


def test_una_cuenta_sin_conectar_no_tumba_la_otra_y_SE_DICE(monkeypatch):
    """EL TEST QUE IMPORTA. Si la de GutLyn no está conectada y Zeno enseña solo la de Zenvrax sin
    avisar, el operador lee "tengo poco correo" cuando la verdad es "falta la mitad"."""
    monkeypatch.setattr(google, "conectadas", lambda: {"zenvrax": {"cuenta": "z"}})
    monkeypatch.setattr(personal, "correos", lambda n, **k: [{"asunto": "uno", "negocio": n}])
    monkeypatch.setattr(personal, "agenda", lambda n, **k: [])
    datos, fallos = personal.bandeja()
    assert len(datos["correos"]) == 1
    assert any("gutlyn.com" in f for f in fallos), (
        "la cuenta que falta tiene que aparecer en los fallos, no desaparecer")


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


def test_zeno_solo_hace_GET_contra_google():
    """Con los permisos de hoy ni siquiera podría escribir, pero el día que se abra el tramo de
    enviar, este test es lo que impide que se cuele por aquí en vez de por el catálogo."""
    fuente = (RAIZ / "servicio" / "google.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("def pide("):]
    assert "method=" not in cuerpo or 'method="GET"' in cuerpo, (
        "la función de leer de Google acepta otro método")
    arbol = ast.parse((RAIZ / "servicio" / "personal.py").read_text(encoding="utf-8"))
    llamadas = [n.func.attr for n in ast.walk(arbol) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.value.__class__.__name__ == "Name"
                and getattr(n.func.value, "id", "") == "google"]
    assert set(llamadas) <= {"pide", "conectadas"}, (
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
    for v in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID_GUTLYN"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(google.SinConfigurar) as e:
        google.enlace_para_autorizar("gutlyn")
    assert "GUTLYN" in str(e.value)


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

    enlace_g = google.enlace_para_autorizar("gutlyn")
    otros = urllib.parse.parse_qs(urllib.parse.urlparse(enlace_g).query)
    assert otros["hd"] == ["gutlyn.com"], "cada cuenta acota a SU dominio, no a uno fijo"


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
