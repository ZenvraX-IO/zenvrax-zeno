# -*- coding: utf-8 -*-
"""Entrar en Zeno: ni se salta el segundo factor, ni confunde "caído" con "no autorizado".

EL CASO. El operador eligió login de verdad, no un token en un enlace, porque en J4 Zeno va a
ejecutar cosas que publican en su nombre. Zeno no tiene usuarios propios: delega en el cockpit, que
ya tiene doble factor en producción.

Lo que estos tests protegen son las tres formas de romperlo sin que nada falle a la vista:

1. Que Zeno se salte el segundo factor. El cockpit responde `twofa_required` y, si Zeno lo ignora y
   deja entrar, el doble factor deja de existir sin que nadie borre una línea de seguridad.
2. Que confunda "el cockpit no responde" con "no autorizado". Tratarlo como no autorizado echa al
   operador de una sesión buena cada vez que el cockpit se reinicia, que es exactamente el incidente
   de agosto en el propio cockpit. Tratarlo como autorizado deja entrar sin comprobar.
3. Que la caché mantenga viva una sesión revocada más de lo debido.

Puros: sin red. Las respuestas del cockpit se sustituyen.
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import sesion                                  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio():
    sesion.limpiar_cache()
    yield
    sesion.limpiar_cache()


def _responde(respuestas):
    """Sustituye la llamada al cockpit. `respuestas` mapea ruta -> dict o excepción."""
    def falso(ruta, cuerpo=None, cabeceras=None):
        r = respuestas[ruta]
        if isinstance(r, Exception):
            raise r
        return r
    return falso


# ------------------------------------------------------------- el segundo factor no se salta

def test_zeno_no_puede_saltarse_el_segundo_factor(monkeypatch):
    """Si el cockpit pide 2FA, Zeno devuelve el challenge y NO un token. Zeno no puede relajar una
    comprobación de seguridad que no es suya."""
    monkeypatch.setattr(sesion, "_pide", _responde(
        {"/auth/login": {"twofa_required": True, "challenge": "ch-123"}}))
    r = sesion.entrar("a@b.c", "x")
    assert r.get("twofa_required") is True
    assert "token" not in r, "con 2FA activo no puede salir un token del primer paso"


def test_el_segundo_paso_devuelve_el_token(monkeypatch):
    monkeypatch.setattr(sesion, "_pide", _responde({"/auth/login/2fa": {"token": "jwt-bueno"}}))
    assert sesion.entrar_2fa("ch-123", "123456")["token"] == "jwt-bueno"


# ------------------------------------------------------------- caído no es lo mismo que denegado

def test_el_cockpit_caido_no_se_confunde_con_sesion_invalida(monkeypatch):
    """EL TEST QUE IMPORTA. Son dos excepciones distintas a propósito: quien las use arriba tiene que
    poder devolver 503 y no 401, que es lo que salva la sesión durante un despliegue."""
    monkeypatch.setattr(sesion, "_pide", _responde(
        {"/auth/me": sesion.CockpitNoResponde("timeout")}))
    with pytest.raises(sesion.CockpitNoResponde):
        sesion.quien_es("jwt")
    assert not issubclass(sesion.CockpitNoResponde, sesion.NoAutenticado)
    assert not issubclass(sesion.NoAutenticado, sesion.CockpitNoResponde)


def test_un_token_rechazado_no_pasa(monkeypatch):
    monkeypatch.setattr(sesion, "_pide", _responde({"/auth/me": sesion.NoAutenticado("401")}))
    with pytest.raises(sesion.NoAutenticado):
        sesion.quien_es("jwt-malo")


def test_sin_token_no_se_pregunta_siquiera():
    with pytest.raises(sesion.NoAutenticado):
        sesion.quien_es("")


def test_un_200_sin_identidad_no_vale(monkeypatch):
    """Si el cockpit contesta 200 pero sin decir quién es, dar por bueno eso sería aceptar cualquier
    200 que venga de donde sea."""
    monkeypatch.setattr(sesion, "_pide", _responde({"/auth/me": {"ok": True}}))
    with pytest.raises(sesion.NoAutenticado):
        sesion.quien_es("jwt")


# ------------------------------------------------------------- la cache no alarga una sesion muerta

def test_la_cache_evita_preguntar_en_cada_pantalla(monkeypatch):
    llamadas = []

    def contando(ruta, cuerpo=None, cabeceras=None):
        llamadas.append(ruta)
        return {"id": "u1", "role": "operator", "email": "a@b.c"}

    monkeypatch.setattr(sesion, "_pide", contando)
    sesion.quien_es("jwt", ahora=1000.0)
    sesion.quien_es("jwt", ahora=1030.0)
    assert len(llamadas) == 1, "dentro de la ventana no se vuelve a preguntar"


def test_la_cache_caduca_y_se_vuelve_a_preguntar(monkeypatch):
    """Sin caducidad, un `logout-all` en el cockpit no cerraría la sesión de Zeno hasta reiniciarlo."""
    llamadas = []

    def contando(ruta, cuerpo=None, cabeceras=None):
        llamadas.append(ruta)
        return {"id": "u1", "role": "operator"}

    monkeypatch.setattr(sesion, "_pide", contando)
    sesion.quien_es("jwt", ahora=1000.0)
    sesion.quien_es("jwt", ahora=1000.0 + sesion.CACHE_SEGUNDOS + 1)
    assert len(llamadas) == 2
    assert sesion.CACHE_SEGUNDOS <= 300, (
        "una sesión revocada no puede seguir entrando minutos: el cockpit invalida por token_version "
        "y Zeno tiene que enterarse pronto")


def test_salir_tira_la_cache(monkeypatch):
    llamadas = []

    def contando(ruta, cuerpo=None, cabeceras=None):
        llamadas.append(ruta)
        return {"id": "u1", "role": "operator"}

    monkeypatch.setattr(sesion, "_pide", contando)
    sesion.quien_es("jwt", ahora=1000.0)
    sesion.olvidar("jwt")
    sesion.quien_es("jwt", ahora=1001.0)
    assert len(llamadas) == 2, "tras salir hay que volver a verificar"


# ------------------------------------------------------------- Zeno no guarda secretos

def test_zeno_no_guarda_contrasenas_ni_firma_tokens():
    """La razón de delegar: si Zeno no almacena nada, no hay nada que robarle. Un `jwt.encode` o un
    hash de contraseña aquí significaría que alguien le dio identidad propia sin decirlo."""
    src = (RAIZ / "servicio" / "sesion.py").read_text(encoding="utf-8")
    for prohibido in ("jwt.encode", "bcrypt", "password_hash", "hashpw", "secret_key", "SECRET"):
        assert prohibido not in src, (
            f"Zeno no puede manejar {prohibido}: su identidad la pone el cockpit")
