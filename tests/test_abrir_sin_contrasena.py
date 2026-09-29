# -*- coding: utf-8 -*-
"""Abrir el cockpit o Xrise desde Zeno sin volver a escribir la contraseña.

EL CASO (2026-09-29). El operador: *"una vez que le doy a abrir desde su plataforma... me envía a
internet y de ahí tengo que volver a validar la contraseña y todo, y no tiene mucho sentido"*.

En el iPhone cada aplicación instalada tiene su propio almacén, separado de Safari. Zeno abre el
enlace en otro almacén, donde no hay sesión. Saltar de una aplicación instalada a otra no existe en
iOS, así que se pide al sistema de destino un enlace de un solo uso.

LAS DOS COSAS QUE SE PRUEBAN AQUÍ, y son opuestas: que Zeno no pida ese enlace para una dirección
que no es de sus dos casas, y que si algo falla el operador pueda abrir igualmente.
"""
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def ent(monkeypatch):
    monkeypatch.setenv("ZENO_WRITE_KEY", "la-de-escribir")
    from servicio import entrada
    return importlib.reload(entrada)


# ---------------------------------------------------------------- de quién es cada dirección

def test_reconoce_las_dos_casas(ent):
    assert ent.de_quien_es("https://cockpit.zenvrax.com/ops/tareas") == "cockpit"
    assert ent.de_quien_es("https://xrise.zenvrax.com/contenido") == "xrise"


def test_no_pide_enlace_para_una_direccion_ajena(ent):
    """LA BARRERA. Si Zeno pidiera un enlace de entrada por cualquier dirección, bastaría una que
    se PAREZCA a la del cockpit para que le entregara una llave a otro sitio."""
    for ajena in ("https://cockpit.zenvrax.com.otrositio.com/x",   # el clásico: empieza igual
                  "https://evil.com/?x=cockpit.zenvrax.com",
                  "https://notcockpit.zenvrax.com/",
                  "https://linkedin.com/feed", "https://n8n.zenvrax.com/", "", "no-es-una-url"):
        assert ent.de_quien_es(ajena) == "", ajena
        assert ent.enlace_que_entra(ajena) == "", ajena


def test_la_ruta_se_conserva_entera(ent):
    """El enlace tiene que devolver a la MISMA pantalla, con su filtro y su ancla. Si se perdiera
    la parte de detrás, el operador entraría en la portada y tendría que buscar lo que miraba."""
    assert ent._ruta("https://cockpit.zenvrax.com/marketing?cola=x#a") == "/marketing?cola=x#a"
    assert ent._ruta("https://cockpit.zenvrax.com") == "/"


# ---------------------------------------------------------------- si algo falla, se abre igual

def test_un_sistema_caido_no_deja_al_operador_sin_abrir(ent, monkeypatch):
    """Degradar, no romper. Sin esto, una caída del cockpit convertiría todos los botones de Zeno
    en botones muertos, cuando antes al menos abrían pidiendo la contraseña."""
    def _cae(*a, **k):
        raise OSError("no responde")

    monkeypatch.setattr(ent.urllib.request, "urlopen", _cae)
    assert ent.enlace_que_entra("https://cockpit.zenvrax.com/ops") == ""


def test_sin_clave_no_se_intenta_siquiera(monkeypatch):
    """Zeno no tiene llave propia de las otras casas: sin la clave no hay nada que pedir."""
    monkeypatch.setenv("ZENO_WRITE_KEY", "")
    from servicio import entrada
    e = importlib.reload(entrada)
    assert e.enlace_que_entra("https://cockpit.zenvrax.com/ops") == ""


def test_lo_que_devuelve_el_sistema_tambien_se_comprueba(ent, monkeypatch):
    """Si el destino contestara con una dirección de otro dominio, Zeno estaría mandando al
    operador fuera con la confianza de haberlo abierto él."""
    import json as _json

    class _R:
        def __init__(self, url): self._u = url
        def read(self): return _json.dumps({"url": self._u}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(ent.urllib.request, "urlopen",
                        lambda req, timeout=0: _R("https://evil.com/entrar?t=x"))
    assert ent.enlace_que_entra("https://cockpit.zenvrax.com/ops") == ""

    monkeypatch.setattr(ent.urllib.request, "urlopen",
                        lambda req, timeout=0: _R("https://cockpit.zenvrax.com/api/auth/entrar?t=x"))
    assert ent.enlace_que_entra("https://cockpit.zenvrax.com/ops").startswith(
        "https://cockpit.zenvrax.com/")


def test_le_pide_el_enlace_al_sistema_correcto(ent, monkeypatch):
    """Pedirle a Xrise un enlace para una pantalla del cockpit devolvería una llave de la casa
    equivocada, y el operador acabaría en un sitio que no era."""
    import json as _json
    visto = {}

    class _R:
        def read(self): return _json.dumps(
            {"url": "https://xrise.zenvrax.com/api/auth/entrar?t=x"}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _mira(req, timeout=0):
        visto["url"] = req.full_url
        visto["clave"] = req.headers.get("X-zeno-key")
        visto["destino"] = _json.loads(req.data)["destino"]
        return _R()

    monkeypatch.setattr(ent.urllib.request, "urlopen", _mira)
    ent.enlace_que_entra("https://xrise.zenvrax.com/contenido?f=1")
    assert "ecomops-api" in visto["url"] and visto["url"].endswith("/auth/entrada")
    assert visto["clave"] == "la-de-escribir"
    assert visto["destino"] == "/contenido?f=1"


# ---------------------------------------------------------------- la pantalla

WEB = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def test_los_enlaces_se_interceptan_en_un_solo_sitio():
    """Había DIEZ `<a href>` hacia las dos casas repartidos por la pantalla. Engancharlos uno a
    uno habría dejado fuera el primero que alguien añadiera después."""
    assert 'document.addEventListener("click"' in WEB
    assert 'closest("a[href]")' in WEB
    assert "cockpit.zenvrax.com" in WEB and "xrise.zenvrax.com" in WEB


def test_la_pestana_se_abre_antes_de_pedir_el_enlace():
    """Safari solo deja abrir una pestaña como respuesta DIRECTA a un toque. Abrirla después del
    `await` la bloquea, y el botón se queda sin hacer nada: el peor resultado posible."""
    i = WEB.index('document.addEventListener("click"')
    bloque = WEB[i:i + 1800]
    assert bloque.index("window.open(") < bloque.index("await api("), (
        "la pestaña se abre después de esperar: Safari la bloqueará")


def test_si_falla_se_abre_el_enlace_de_siempre():
    i = WEB.index('document.addEventListener("click"')
    bloque = WEB[i:i + 1800]
    assert "catch" in bloque and bloque.count("a.href") >= 2, (
        "no hay camino de vuelta al enlace normal cuando algo falla")
