# -*- coding: utf-8 -*-
"""El borrador: lo que separa redactar de enviar, y todo lo que puede borrar esa línea.

EL CASO. Enviar un correo sale al mundo igual que publicar un post: llega a un cliente y no se
recoge. Un borrador no sale del buzón. Toda esta pieza existe para que esa diferencia sea real y no
una promesa, así que lo que hay que blindar es exactamente eso: que nunca, por ningún camino, esto
acabe enviando algo.

Las seis formas de romperlo:

1. Que se llame a `send` en vez de a `drafts`.
2. Que preparar ya escriba en Gmail.
3. Que un vale sirva dos veces y aparezcan dos borradores iguales.
4. Que el borrador se mande al remitente equivocado.
5. Que rompa el hilo, y quien lo reciba vea una conversación nueva sin contexto.
6. Que el cuerpo del correo leído acabe guardado en algún sitio.

Puros: sin red.
"""
import pathlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import correo, google                    # noqa: E402

ENTERO = {
    "id": "m1", "hilo": "h1", "de": "Cliente <cliente@empresa.com>",
    "para": "ghidalgo@zenvrax.com", "asunto": "Presupuesto de septiembre",
    "mensaje_id": "<abc@empresa.com>", "referencias": "",
    "cuerpo": "Hola, cuando podemos hablar del presupuesto?",
}


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    correo._VALES.clear()
    monkeypatch.setattr(correo, "lee_entero", lambda n, i, tope=4000: dict(ENTERO))
    yield
    correo._VALES.clear()


def _nada_se_escribe(monkeypatch):
    def no(*a, **k):
        raise AssertionError("ha escrito en Gmail sin confirmar")
    monkeypatch.setattr(google, "escribe", no)


def _escribe_bien(monkeypatch, visto):
    monkeypatch.setattr(google, "escribe",
                        lambda n, url, cuerpo, metodo="POST":
                        visto.append((url, cuerpo, metodo)) or {"id": "d1"})


# ---------------------------------------------------------------- nunca envia

def test_solo_hay_UN_camino_que_envia_y_pasa_por_el_borrador():
    """EL TEST QUE IMPORTA, estrechado el 28-sep en vez de quitado.

    Hasta ese dia decia que NINGUNA llamada podia enviar, y ya avisaba de lo que acabo siendo
    cierto: *"el tramo de permisos de Google no lo impediria: `gmail.compose` deja hacer las dos
    cosas"*. Tenia razon y el comentario de `google.py` decia lo contrario. La barrera nunca
    estuvo en el permiso.

    Ahora enviar existe, asi que lo que se defiende es COMO: un solo camino, por el borrador, y
    nunca `messages/send` directo, que mandaria el correo sin dejar copia si algo falla.
    """
    fuente = _solo_el_codigo(RAIZ / "servicio" / "correo.py")
    assert "messages/send" not in fuente, (
        "envio directo: si falla a mitad, el texto escrito se pierde")
    assert fuente.count("/drafts/send") == 1, "hay mas de un camino que envia, o ninguno"
    assert "/drafts" in fuente, "y el de borradores tiene que seguir existiendo"


def test_el_envio_crea_el_borrador_antes_de_mandarlo(monkeypatch):
    """Los dos pasos son la red de seguridad: si el envio falla, el texto esta en Gmail. Con un
    solo paso, un fallo se lleva por delante lo que el operador acababa de escribir."""
    escrito = []
    monkeypatch.setattr(correo.google, "escribe",
                        lambda n, url, cuerpo: escrito.append(url) or {"id": "d1"})
    monkeypatch.setattr(correo, "lee_entero", lambda n, i, tope=4000: {
        "de": "Ana <ana@cliente.com>", "asunto": "Hola", "hilo": "h1",
        "mensaje_id": "<m1>", "referencias": ""})
    monkeypatch.setattr(correo, "contesta_alguien", lambda d: True)
    v = correo.prepara("zenvrax", "m1", "Te llamo el jueves.")["vale"]
    salida = correo.envia(v)
    assert [u.rsplit("/v1/users/me", 1)[-1] for u in escrito] == ["/drafts", "/drafts/send"], escrito
    assert salida["enviado"] is True and salida["id"] == "d1"


def test_si_no_se_sabe_si_salio_NO_se_dice_que_fallo(monkeypatch):
    """Un timeout despues de mandar la peticion puede significar que el correo ya se fue. Decir
    "no se ha enviado" invita a reintentar, y reintentar manda el correo dos veces al cliente."""
    def _escribe(n, url, cuerpo):
        if url.endswith("/drafts"):
            return {"id": "d1"}
        raise TimeoutError("se corto")

    monkeypatch.setattr(correo.google, "escribe", _escribe)
    monkeypatch.setattr(correo, "lee_entero", lambda n, i, tope=4000: {
        "de": "Ana <ana@cliente.com>", "asunto": "Hola", "hilo": "h1",
        "mensaje_id": "<m1>", "referencias": ""})
    monkeypatch.setattr(correo, "contesta_alguien", lambda d: True)
    v = correo.prepara("zenvrax", "m1", "Te llamo el jueves.")["vale"]
    try:
        correo.envia(v)
    except correo.NoSeSabe as e:
        assert "Enviados" in str(e), "no dice donde comprobarlo antes de repetir"
        assert "no he podido" not in str(e).lower() or "saber" in str(e).lower()
    else:
        raise AssertionError("un envio de resultado desconocido se dio por bueno")


def test_un_vale_gastado_no_puede_enviar_otra_vez(monkeypatch):
    """Sin esto, pulsar dos veces manda el correo dos veces."""
    monkeypatch.setattr(correo.google, "escribe", lambda n, url, cuerpo: {"id": "d1"})
    monkeypatch.setattr(correo, "lee_entero", lambda n, i, tope=4000: {
        "de": "Ana <ana@cliente.com>", "asunto": "Hola", "hilo": "h1",
        "mensaje_id": "<m1>", "referencias": ""})
    monkeypatch.setattr(correo, "contesta_alguien", lambda d: True)
    v = correo.prepara("zenvrax", "m1", "Te llamo el jueves.")["vale"]
    correo.envia(v)
    try:
        correo.envia(v)
    except correo.NoSePuede:
        pass
    else:
        raise AssertionError("el mismo vale ha enviado dos veces")


def test_lo_que_se_manda_a_gmail_es_un_borrador(monkeypatch):
    visto = []
    _escribe_bien(monkeypatch, visto)
    v = correo.prepara("zenvrax", "m1", "Te llamo el jueves.")["vale"]
    r = correo.guarda(v)
    url, cuerpo, metodo = visto[0]
    assert url.endswith("/drafts") and metodo == "POST"
    assert "message" in cuerpo and "raw" in cuerpo["message"]
    assert r["enviado"] is False and r["guardado"] is True


def test_preparar_no_escribe_en_gmail(monkeypatch):
    _nada_se_escribe(monkeypatch)
    p = correo.prepara("zenvrax", "m1", "Te llamo el jueves.")
    # `solo_borrador` paso a False el 28-sep: el mismo vale sirve para guardar y para enviar, asi
    # que prepara() ya no puede prometer que no se envia. Lo decide el boton que se pulse, y por
    # eso la respuesta avisa de que uno de los dos sale al mundo.
    assert p["vale"] and p["solo_borrador"] is False
    assert p["enviar_sale_al_mundo"] is True
    assert "borrador" in p["que_pasa"] and "enviarlo" in p["que_pasa"]


def test_un_vale_sirve_una_sola_vez(monkeypatch):
    """Dos borradores iguales en la bandeja son dos correos a medias que alguien acaba mandando."""
    visto = []
    _escribe_bien(monkeypatch, visto)
    v = correo.prepara("zenvrax", "m1", "Vale.")["vale"]
    correo.guarda(v)
    with pytest.raises(correo.NoSePuede):
        correo.guarda(v)
    assert len(visto) == 1


def test_un_borrador_vacio_no_se_prepara(monkeypatch):
    _nada_se_escribe(monkeypatch)
    for vacio in ("", "   ", "\n"):
        with pytest.raises(correo.NoSePuede):
            correo.prepara("zenvrax", "m1", vacio)


# ---------------------------------------------------------------- va a quien tiene que ir

def test_el_borrador_responde_a_quien_escribio():
    """Mandar la respuesta a la direccion equivocada es el fallo silencioso de esta pieza: el
    borrador parece bien hecho y va al sitio que no es."""
    p = correo.prepara("zenvrax", "m1", "Vale.")
    assert p["para"] == "cliente@empresa.com", "sin el nombre ni los picos"


def test_un_correo_sin_remitente_no_se_contesta(monkeypatch):
    monkeypatch.setattr(correo, "lee_entero", lambda n, i, tope=4000: {**ENTERO, "de": ""})
    with pytest.raises(correo.NoSePuede) as e:
        correo.prepara("zenvrax", "m1", "Vale.")
    assert "a quien" in str(e.value)


def test_el_asunto_lleva_Re_una_sola_vez(monkeypatch):
    assert correo.prepara("zenvrax", "m1", "x")["asunto"] == "Re: Presupuesto de septiembre"
    monkeypatch.setattr(correo, "lee_entero",
                        lambda n, i, tope=4000: {**ENTERO, "asunto": "Re: Ya contestado"})
    assert correo.prepara("zenvrax", "m1", "x")["asunto"] == "Re: Ya contestado"


def test_el_borrador_se_queda_en_el_hilo(monkeypatch):
    """Sin `threadId` y sin `In-Reply-To`, el borrador sale suelto: quien lo recibe ve una
    conversacion nueva y pierde el contexto de lo que se estaba contestando."""
    visto = []
    _escribe_bien(monkeypatch, visto)
    correo.guarda(correo.prepara("zenvrax", "m1", "Vale.")["vale"])
    cuerpo = visto[0][1]
    assert cuerpo["message"]["threadId"] == "h1"
    import base64
    crudo = base64.urlsafe_b64decode(cuerpo["message"]["raw"]).decode()
    assert "In-Reply-To: <abc@empresa.com>" in crudo
    assert "References: <abc@empresa.com>" in crudo


def test_el_texto_del_operador_llega_tal_cual(monkeypatch):
    """Zeno no reescribe lo que el operador ha escrito. Si lo tocara, lo que se manda no seria lo
    que se aprobo."""
    visto = []
    _escribe_bien(monkeypatch, visto)
    texto = "Hola Ana, el jueves a las 10 me viene bien. Un saludo, Gustavo"
    correo.guarda(correo.prepara("zenvrax", "m1", texto)["vale"])
    import base64
    crudo = base64.urlsafe_b64decode(visto[0][1]["message"]["raw"]).decode()
    assert texto in crudo


# ---------------------------------------------------------------- no guarda el correo leido

def test_el_cuerpo_leido_no_se_guarda_en_disco():
    """Aqui se lee el cuerpo entero de UN correo, que es una excepcion deliberada a como se lee la
    bandeja. La excepcion vale mientras ese cuerpo se use y se olvide: una copia seria el tercer
    sitio con los datos personales del operador."""
    import ast
    arbol = ast.parse((RAIZ / "servicio" / "correo.py").read_text(encoding="utf-8"))
    escrituras = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr in ("write_text", "write_bytes", "dump", "execute")]
    assert not escrituras, [n.func.attr for n in escrituras]


# ---------------------------------------------------------------- a quien no lee nadie

def test_se_avisa_cuando_la_direccion_no_la_lee_nadie(monkeypatch):
    """SALIO DE LA PRIMERA PRUEBA REAL. El correo sin leer mas reciente era un aviso de Facebook, y
    Zeno preparo una respuesta a `pageupdates@facebookmail.com` tan tranquilo. El borrador estaba
    impecable y no servia para nada.

    Se AVISA, no se bloquea: alguna de esas direcciones sale de un buzon que si atiende gente, y
    decidir por el operador que un correo no merece respuesta seria pasarse.
    """
    monkeypatch.setattr(correo, "lee_entero", lambda n, i, tope=4000: {
        **ENTERO, "de": "Facebook <pageupdates@facebookmail.com>"})
    p = correo.prepara("zenvrax", "m1", "Vale.")
    assert p["nadie_lo_lee"] is True
    assert p["vale"], "pero se puede preparar igual: es un aviso, no una prohibicion"


def test_una_persona_de_verdad_no_lleva_el_aviso():
    """Si saltara de mas, el aviso se leeria sin mirarlo y no diria nada."""
    assert correo.prepara("zenvrax", "m1", "Vale.")["nadie_lo_lee"] is False


def test_las_direcciones_que_no_leen_a_nadie():
    for muerta in ("noreply@empresa.com", "no-reply@x.io", "NoReply@X.COM",
                   "notifications@github.com", "pageupdates@facebookmail.com",
                   "mailer-daemon@google.com"):
        assert correo.contesta_alguien(muerta) is False, muerta
    for viva in ("ana@cliente.com", "info@ecommheroacademy.com", "ghidalgo@gutlyn.com"):
        assert correo.contesta_alguien(viva) is True, viva


def _solo_el_codigo(ruta) -> str:
    """El fichero SIN docstrings ni comentarios.

    La primera version buscaba en el texto crudo y saltaba por un comentario que explicaba
    precisamente que NO se usa `messages/send`. Un guardian que no distingue lo que el codigo hace
    de lo que el codigo cuenta obliga a no escribir comentarios, que es el peor de los arreglos.
    """
    import ast as _ast
    arbol = _ast.parse(pathlib.Path(ruta).read_text(encoding="utf-8"))
    for nodo in _ast.walk(arbol):
        if not isinstance(nodo, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                                 _ast.ClassDef)):
            continue
        cuerpo = getattr(nodo, "body", [])
        if (cuerpo and isinstance(cuerpo[0], _ast.Expr)
                and isinstance(cuerpo[0].value, _ast.Constant)
                and isinstance(cuerpo[0].value.value, str)):
            cuerpo.pop(0)
            if not cuerpo:                      # una funcion que solo era su docstring
                cuerpo.append(_ast.Pass())
    return _ast.unparse(arbol)
