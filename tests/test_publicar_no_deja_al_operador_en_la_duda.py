# -*- coding: utf-8 -*-
"""Publicar no bloquea la pantalla, y lo que no se sabe se pregunta en vez de dudarse.

EL CASO (2026-09-30). El operador pulsó Publicar en un post de GutLyn, la pantalla se quedó parada
y acabó diciendo *"no se ha podido saber si salió (TimeoutError): comprueba en el sistema antes de
repetirlo"*. Había salido. Medido en la ejecución real de B08:

    58,6s en total, de los cuales:
      18,0s  IG Publish Media        \\
      13,3s  IG Create Container      |  57s son la API de Meta. Instagram no deja publicar de
      11,5s  FB Post Photo            |  una vez: crea un contenedor, espera a que procese la
       8,0s  Wait IG Container        |  imagen, y solo entonces publica.
       6,3s  FB Get Page Token       /
       0,0s  todo el trabajo de n8n (ClickUp, Postgres, Slack, validador, 19 pasos)

Zeno esperaba 45. Su respuesta: *"tarda mucho en aprobarse y no existe un thick que lo muestre como
publicado... se debe comprobar in situ y es algo a evitar"*.

DOS COSAS DISTINTAS SE ARREGLAN AQUÍ, y conviene no confundirlas:

  1. El minuto de Meta NO se puede quitar, pero no tiene por qué comérselo quien mira: lo que
     publica sale en segundo plano y devuelve un encargo.
  2. Un timeout NO es una duda cuando el sistema sabe contestar si aquello salió. Para eso está
     `comprobar` en el contrato, y por eso el campo tiene que VIAJAR hasta el front y volver.
"""
import json
import sys
import time
import urllib.error
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import ejecutor  # noqa: E402

PUBLICAR = "http://ecomops-api:8803/content/gutlyn/11111111-2222-3333-4444-555555555555/action"
WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def _acaba(encargo, tope=6.0):
    limite = time.time() + tope
    while time.time() < limite:
        r = ejecutor.como_va(encargo)
        if r["estado"] != "en_marcha":
            return r
        time.sleep(0.02)
    raise AssertionError("el encargo se ha quedado en marcha")


def _propone(monkeypatch, comprobar="estado"):
    monkeypatch.setattr(ejecutor, "CLAVE_LECTURA", "una-clave")
    return ejecutor.propone("gutlyn.aprobar_y_publicar", "Aprobar y publicar", PUBLICAR,
                            ejecutor.PUBLICA, titulo="W5/P16", metodo="POST",
                            cuerpo={"action": "publish"}, comprobar=comprobar)["vale"]


# ------------------------------------------------------------------ 1. no se come el minuto

def test_publicar_devuelve_el_control_al_instante(monkeypatch):
    """LO QUE EL OPERADOR PIDIÓ. Si `confirma` volviera a esperar, la pantalla se quedaría parada
    el minuto entero de Meta, que es justo de lo que se quejó."""
    def lento(*a, **k):
        time.sleep(3)
        raise TimeoutError("Meta tarda")
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", lento)
    v = _propone(monkeypatch, comprobar="")

    t0 = time.time()
    r = ejecutor.confirma(v, pin_abierto=True)
    tardo = time.time() - t0

    assert tardo < 1.0, f"confirma ha bloqueado {tardo:.1f}s: se come la espera de Meta"
    assert r["en_marcha"] is True and r["encargo"], "no devuelve un encargo que vigilar"
    _acaba(r["encargo"])


def test_lo_que_solo_cambia_un_estado_SI_se_espera(monkeypatch):
    """El otro lado, para no pasarse de listo: regenerar es inmediato. Devolver un encargo para
    algo que tarda medio segundo obligaría a la pantalla a preguntar por nada."""
    class Ok:
        status = 200
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", lambda *a, **k: Ok())
    v = ejecutor.propone("x", "Regenerar", PUBLICAR, ejecutor.CAMBIA_ESTADO)["vale"]
    r = ejecutor.confirma(v, pin_abierto=False)
    assert r["hecho"] is True and "en_marcha" not in r


# ------------------------------------------------------------------ 2. la duda se pregunta

def test_un_timeout_se_resuelve_PREGUNTANDO_si_salio(monkeypatch):
    """EL CORAZÓN DEL ARREGLO. Antes: "comprueba en el sistema antes de repetirlo". Ahora se le
    pregunta al sistema, que sabe la respuesta, y el operador no tiene que ir a mirar nada."""
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("Meta tarda")))
    monkeypatch.setattr(ejecutor, "pregunta_si_salio",
                        lambda d: {"publicado": True, "en_marcha": False,
                                   "ig_url": "https://instagram.com/p/abc"})
    v = _propone(monkeypatch)
    r = _acaba(ejecutor.confirma(v, pin_abierto=True)["encargo"])

    assert r["estado"] == "hecho", "sigue diciendo que no se sabe, teniendo a quien preguntar"
    assert "comprueba en el sistema" not in r["mensaje"], "sigue mandando al operador a mirarlo"
    assert r["enlaces"].get("ig_url"), "el tic llega sin enlace al post"


def test_si_el_sistema_dice_que_NO_salio_se_dice_que_no(monkeypatch):
    """Y no al revés: preguntar solo vale si la respuesta manda en los dos sentidos. Si un 'no'
    se leyera como 'sí', el operador daría por publicado algo que no salió."""
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("boom")))
    monkeypatch.setattr(ejecutor, "pregunta_si_salio",
                        lambda d: {"publicado": False, "en_marcha": False})
    v = _propone(monkeypatch)
    r = _acaba(ejecutor.confirma(v, pin_abierto=True)["encargo"])
    assert r["estado"] == "error"


def test_sin_a_quien_preguntar_la_duda_SIGUE_siendo_duda(monkeypatch):
    """Lo que NO se puede hacer es inventar. Cuando el sistema no sabe contestar, decir 'publicado'
    sería peor que el fallo original: daría por cerrado lo que no se sabe."""
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("boom")))
    v = _propone(monkeypatch, comprobar="")
    r = _acaba(ejecutor.confirma(v, pin_abierto=True)["encargo"])
    assert r["estado"] == "no_se_sabe"
    assert "NO lo repitas" in r["mensaje"], "sin esto, el operador vuelve a pulsar y publica dos veces"


def test_preguntar_NO_es_reintentar(monkeypatch):
    """LA LÍNEA QUE NO SE PUEDE CRUZAR. Un timeout puede significar que el post YA salió. Si al no
    saberlo se volviera a disparar la acción, se publicaría dos veces."""
    disparos = []
    def cuelga(req, *a, **k):
        disparos.append(getattr(req, "full_url", str(req)))
        raise TimeoutError("boom")
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", cuelga)
    monkeypatch.setattr(ejecutor, "pregunta_si_salio", lambda d: {"publicado": True})
    v = _propone(monkeypatch)
    _acaba(ejecutor.confirma(v, pin_abierto=True)["encargo"])
    assert disparos == [PUBLICAR], f"la accion se ha disparado {len(disparos)} veces: {disparos}"


def test_la_ruta_que_se_pregunta_sale_de_la_de_la_accion():
    """`/content/gutlyn/{id}/action` con `comprobar='estado'` pregunta a `.../estado`, y a nada
    más: si apuntara a otro sitio, la respuesta seria de otro post."""
    d = {"url": PUBLICAR, "comprobar": "estado"}
    assert ejecutor._url_de_comprobar(d) == PUBLICAR.replace("/action", "/estado")
    assert ejecutor._url_de_comprobar({"url": PUBLICAR, "comprobar": ""}) == ""


def test_preguntar_va_con_la_clave_de_LECTURA(monkeypatch):
    """Preguntar no muta nada, asi que no viaja con la llave que escribe."""
    visto = {}
    class Ok:
        def read(self): return json.dumps({"publicado": True}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def mira(req, *a, **k):
        visto.update(req.headers)
        return Ok()
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", mira)
    monkeypatch.setattr(ejecutor, "CLAVE_LECTURA", "la-de-leer")
    monkeypatch.setattr(ejecutor, "CLAVE_ESCRITURA", "la-de-escribir")
    ejecutor.pregunta_si_salio({"url": PUBLICAR, "comprobar": "estado"})
    assert visto.get("X-zeno-key") == "la-de-leer", visto


# ------------------------------------------------------------------ 3. el campo VIAJA

def test_comprobar_viaja_del_catalogo_hasta_la_pantalla():
    """EL FALLO QUE DEJARÍA TODO ESTO DE ADORNO. Un campo declarado y no propagado es peor que no
    declararlo: el código dice que se puede comprobar, y en producción la pantalla nunca lo manda,
    así que el timeout sigue siendo una duda. Se recorre la cadena entera."""
    import catalogo

    # 1) el catalogo lo declara, y en la accion que de verdad lo necesita
    acciones = catalogo.catalogo()
    publica = [a for a in acciones if a.op == "gutlyn.aprobar_y_publicar"]
    assert publica, "no esta la accion de publicar GutLyn"
    assert publica[0].comprobar == "estado", "la accion que tarda un minuto no se puede comprobar"

    # 2) el congelado tambien, que es de donde arranca el contenedor
    crudo = json.loads((RAIZ / "catalogo" / "congelado.json").read_text(encoding="utf-8"))
    cong = [a for a in crudo["acciones"] if a["op"] == "gutlyn.aprobar_y_publicar"]
    assert cong and cong[0].get("comprobar") == "estado", (
        "el congelado no lo lleva: en el contenedor el campo llegaria vacio")

    # 3) el servidor lo entrega a la pantalla, en las DOS serializaciones
    api = (RAIZ / "servicio" / "api.py").read_text(encoding="utf-8")
    assert api.count('"comprobar": a.comprobar') == 2, (
        "una de las dos listas de acciones no lo manda al front")

    # 4) y la pantalla lo devuelve al proponer, en los DOS sitios que proponen
    assert WEB.count("comprobar: accion.comprobar") == 2, (
        "la pantalla propone sin `comprobar`: el servidor no sabria a quien preguntar")


def test_el_congelado_viejo_sigue_cargando():
    """Un campo nuevo no puede dejar a Zeno sin catalogo. El contenedor arranca del congelado, y
    uno escrito antes de que el campo existiera tiene que seguir entrando."""
    from catalogo import Accion
    a = Accion(op="x", que_hace="y", sistema="xrise", efecto="publica", reversible=False,
               coste_api=False, confirmar=True, guarda="ninguna", verbo="POST",
               destino="/x", cuerpo={}, etiqueta="X", linea=1)
    assert a.comprobar == ""


# ------------------------------------------------------------------ 4. la pantalla

def test_la_pantalla_no_se_queda_esperando():
    """Si el front no mirara `en_marcha`, pintaria 'Hecho' sobre algo que aun esta saliendo, que es
    peor que la espera: daria por publicado lo que todavia puede fallar."""
    assert "if (d.en_marcha)" in WEB
    assert "vigilaEncargo(d.encargo" in WEB
    i = WEB.index("if (d.en_marcha)")
    assert "Publicando en Instagram y " in WEB[i:i + 500]


def test_el_tic_de_publicado_existe_y_es_distinto_del_normal():
    """Lo que pidio el operador con todas las letras: *"no existe un thick que lo muestre como
    publicado"*. Y con su estilo propio, porque un 'Hecho' en el mismo color no se distingue."""
    assert "✅ Publicado" in WEB
    assert ".propuesta.publicado{" in WEB, "el tic no tiene estilo propio: se lee como uno mas"


def test_la_pantalla_no_da_por_bueno_lo_que_no_sabe():
    """El encargo perdido (un reinicio de Zeno) no se puede pintar como publicado."""
    i = WEB.index("async function vigilaEncargo")
    cuerpo = WEB[i:i + 2400]
    assert "aviso-fallo" in cuerpo and "cargaPendientes()" in cuerpo
    j = cuerpo.index('e.estado === "hecho"')
    assert "Publicado" in cuerpo[j:j + 600], "el tic no cuelga del estado 'hecho'"


def test_el_encargo_caducado_no_miente():
    """Preguntar por uno que ya no existe no puede contestar que salio bien."""
    with pytest.raises(ejecutor.NoSePuede) as e:
        ejecutor.como_va("no-existe-este-encargo")
    assert "recarga" in str(e.value)
