# -*- coding: utf-8 -*-
"""La clave propia de Zeno: una sola puerta, y todo lo que no puede pasar en ella.

EL CASO. Entrar en Zeno pedía la contraseña del cockpit MAS el código de seis cifras, varias veces al
día y desde el móvil. El operador (2026-09-27): *"no se queda registrada y es un lio"*. Una puerta que
cuesta cruzar se deja de cruzar.

El precio es real: una sola clave, sin segundo factor, en una dirección pública. Así que lo que estos
tests protegen es exactamente eso, las seis formas de que salga mal:

1. Que la clave en claro acabe guardada en algún sitio.
2. Que el hash se compare de una forma que se pueda adivinar byte a byte.
3. Que se pueda probar el diccionario entero sin freno.
4. Que un token se pueda falsificar sin conocer la clave.
5. Que un token caducado siga valiendo.
6. Que la clave propia esquive la lista de quién puede entrar.

Y una séptima que no es de seguridad pero era el motivo del enfado: que un reinicio del contenedor
eche al operador fuera.

Puros: sin red.
"""
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import clave as clave_mod, sesion            # noqa: E402

LA_CLAVE = "una-clave-de-prueba-larga-de-verdad"


@pytest.fixture(autouse=True)
def _con_clave(monkeypatch):
    # Se cifra una vez y se reutiliza: scrypt es caro a propósito, y eso en un test se nota.
    monkeypatch.setattr(clave_mod, "CLAVE_HASH", _HASH)
    clave_mod._fallos.clear()
    yield
    clave_mod._fallos.clear()


_HASH = clave_mod.cifra_clave(LA_CLAVE)


# ---------------------------------------------------------------- la clave no se guarda ni se filtra

def test_el_hash_no_contiene_la_clave():
    """Si el hash llevara la clave dentro, el `.env` del servidor sería la clave en claro."""
    assert LA_CLAVE not in _HASH
    assert _HASH.startswith("scrypt$")


def test_dos_veces_la_misma_clave_dan_hashes_distintos():
    """Sin sal, dos instalaciones con la misma clave tendrían el mismo hash, y una tabla precalculada
    valdría para las dos."""
    assert clave_mod.cifra_clave(LA_CLAVE) != clave_mod.cifra_clave(LA_CLAVE)


def test_el_modulo_no_escribe_en_ningun_sitio():
    """La clave en claro no se guarda: se comprueba y se olvida. Una copia sería el sitio por donde
    se filtra."""
    fuente = (RAIZ / "servicio" / "clave.py").read_text(encoding="utf-8")
    for escribe in ("write_text(", "write_bytes(", "open(", "json.dump("):
        assert escribe not in fuente, f"clave.py escribe con {escribe}"


def test_el_hash_se_compara_en_tiempo_constante():
    """Comparar con `==` corta en el primer byte distinto, y ese tiempo distinto es por donde se
    adivina un hash byte a byte. Este es el test que fija que se use compare_digest."""
    fuente = (RAIZ / "servicio" / "clave.py").read_text(encoding="utf-8")
    assert fuente.count("compare_digest") >= 2, (
        "tanto la clave como la firma del token se comparan en tiempo constante")
    assert "== esperado" not in fuente and "== esperada" not in fuente


# ---------------------------------------------------------------- entrar

def test_la_clave_buena_entra_y_devuelve_un_token():
    d = clave_mod.entrar(LA_CLAVE, "yo@zenvrax.com")
    assert d["token"].startswith("z1.")
    assert clave_mod.lee(d["token"]) == "yo@zenvrax.com"


def test_una_clave_parecida_no_entra():
    for mala in (LA_CLAVE + "x", LA_CLAVE.upper(), LA_CLAVE[:-1], "", "   "):
        with pytest.raises(clave_mod.ClaveMala):
            clave_mod.entrar(mala)


def test_sin_clave_configurada_se_dice_y_no_se_deja_entrar(monkeypatch):
    """El fallo peor sería que "no hay clave puesta" se leyera como "cualquier clave vale"."""
    monkeypatch.setattr(clave_mod, "CLAVE_HASH", "")
    with pytest.raises(clave_mod.ClaveNoConfigurada):
        clave_mod.entrar(LA_CLAVE)
    with pytest.raises(clave_mod.ClaveNoConfigurada):
        clave_mod.entrar("")


def test_un_hash_de_otro_tipo_no_se_da_por_bueno(monkeypatch):
    """Si mañana alguien pega en el `.env` un hash de otra herramienta, esto tiene que negarse en vez
    de comparar mal y dejar pasar."""
    monkeypatch.setattr(clave_mod, "CLAVE_HASH", "bcrypt$sal$loquesea")
    with pytest.raises(clave_mod.ClaveNoConfigurada):
        clave_mod.entrar(LA_CLAVE)
    monkeypatch.setattr(clave_mod, "CLAVE_HASH", "sin-formato")
    with pytest.raises(clave_mod.ClaveNoConfigurada):
        clave_mod.entrar(LA_CLAVE)


def test_tras_varios_fallos_seguidos_se_frena(monkeypatch):
    """Una sola clave sin segundo factor en una dirección pública se prueba en masa. El freno es lo
    que convierte eso en algo que no acaba."""
    ahora = 1000.0
    for _ in range(clave_mod.TOPE_FALLOS):
        with pytest.raises(clave_mod.ClaveMala):
            clave_mod.entrar("mala", ahora=ahora)
    # Y ahora ni la BUENA entra: si el freno solo parase las malas, se podría seguir probando.
    with pytest.raises(clave_mod.ClaveMala) as e:
        clave_mod.entrar(LA_CLAVE, ahora=ahora)
    assert "intentos" in str(e.value)


def test_el_freno_se_suelta_al_pasar_el_castigo():
    """Un freno que no se suelta deja al operador fuera para siempre por ocho erratas."""
    for _ in range(clave_mod.TOPE_FALLOS):
        with pytest.raises(clave_mod.ClaveMala):
            clave_mod.entrar("mala", ahora=1000.0)
    d = clave_mod.entrar(LA_CLAVE, "yo@zenvrax.com", ahora=1000.0 + clave_mod.CASTIGO + 1)
    assert d["token"]


def test_acertar_borra_los_fallos_anteriores():
    """Si no, dos erratas de hoy y seis de la semana que viene sumarían un castigo sin motivo."""
    for _ in range(3):
        with pytest.raises(clave_mod.ClaveMala):
            clave_mod.entrar("mala")
    clave_mod.entrar(LA_CLAVE)
    assert clave_mod._fallos == []


# ---------------------------------------------------------------- los tokens

def test_un_token_con_la_firma_tocada_no_vale():
    """EL TEST QUE IMPORTA. Sin esto, cualquiera escribe su propio token y entra sin la clave."""
    t = clave_mod.emite("yo@zenvrax.com")
    cabeza, cuerpo, firma = t.split(".")
    # El ultimo caracter se cambia por OTRO, no por un "0" fijo: con un "0", una vez de cada
    # dieciseis la firma ya acababa en "0" y el token "falsificado" era el bueno. Un test que falla
    # una vez de cada dieciseis es peor que no tenerlo, porque se acaba ignorando.
    otro = "1" if firma[-1] != "1" else "2"
    for falso in (f"{cabeza}.{cuerpo}.{'0' * 32}",
                  f"{cabeza}.{cuerpo}.{firma[:-1]}{otro}",
                  f"{cabeza}.{cuerpo}."):
        with pytest.raises(clave_mod.ClaveMala):
            clave_mod.lee(falso)


def test_cambiar_el_cuerpo_invalida_la_firma():
    """Un token es un sobre abierto: se lee. Lo que no se puede es reescribirlo."""
    import base64
    import json
    t = clave_mod.emite("yo@zenvrax.com")
    _, _, firma = t.split(".")
    otro = base64.urlsafe_b64encode(
        json.dumps({"c": "intruso@fuera.com", "exp": 9e9}).encode()).decode().rstrip("=")
    with pytest.raises(clave_mod.ClaveMala):
        clave_mod.lee(f"z1.{otro}.{firma}")


def test_un_token_caducado_no_vale():
    t = clave_mod.emite("yo@zenvrax.com", ahora=time.time() - clave_mod.DURACION - 10)
    with pytest.raises(clave_mod.ClaveMala) as e:
        clave_mod.lee(t)
    assert "caducado" in str(e.value)


def test_cambiar_la_clave_invalida_las_sesiones_abiertas(monkeypatch):
    """Es la única forma de echar a todo el mundo sin llevar una lista de tokens vivos. Si la firma
    dependiera de un secreto aparte, cambiar la clave dejaría las sesiones viejas dentro."""
    t = clave_mod.emite("yo@zenvrax.com")
    assert clave_mod.lee(t) == "yo@zenvrax.com"
    monkeypatch.setattr(clave_mod, "CLAVE_HASH", clave_mod.cifra_clave("otra clave distinta"))
    with pytest.raises(clave_mod.ClaveMala):
        clave_mod.lee(t)


def test_el_token_no_depende_de_la_memoria_del_proceso():
    """Era el motivo del enfado: guardar las sesiones en memoria hacía que cada despliegue de Zeno
    echara al operador fuera. Un token firmado se verifica sin estado, así que sobrevive."""
    t = clave_mod.emite("yo@zenvrax.com")
    clave_mod._fallos.clear()                    # lo único que hay en memoria, y no afecta
    assert clave_mod.lee(t) == "yo@zenvrax.com"


# ---------------------------------------------------------------- no esquiva la guarda

def test_la_clave_propia_no_salta_la_lista_de_quien_puede_entrar(monkeypatch):
    """`ZENO_USUARIOS` existe porque Zeno tiene UN usuario. Una puerta nueva que no la respetara
    dejaría la guarda puesta y sin efecto, que es peor que no tenerla."""
    monkeypatch.setattr(sesion, "USUARIOS", ["ghidalgo@zenvrax.com"])
    bueno = clave_mod.emite("ghidalgo@zenvrax.com")
    assert sesion.quien_es(bueno).email == "ghidalgo@zenvrax.com"

    colado = clave_mod.emite("otro@zenvrax.com")
    with pytest.raises(sesion.NoAutenticado) as e:
        sesion.quien_es(colado)
    assert "acceso a Zeno" in str(e.value)


def test_un_token_de_zeno_no_va_a_preguntar_al_cockpit(monkeypatch):
    """Es media gracia de tener clave propia: con el cockpit caído se sigue entrando."""
    def revienta(*a, **k):
        raise AssertionError("no se puede preguntar al cockpit por un token propio")
    monkeypatch.setattr(sesion, "_pide", revienta)
    monkeypatch.setattr(sesion, "USUARIOS", [])
    assert sesion.quien_es(clave_mod.emite("yo@zenvrax.com")).role == "owner"


def test_un_token_del_cockpit_sigue_yendo_al_cockpit(monkeypatch):
    """La puerta vieja sigue entera: esta clave se suma, no sustituye."""
    visto = []
    monkeypatch.setattr(sesion, "USUARIOS", [])
    monkeypatch.setattr(sesion, "_pide", lambda ruta, cuerpo=None, cabeceras=None: visto.append(ruta)
                        or {"id": "u1", "role": "owner", "email": "yo@zenvrax.com"})
    sesion.limpiar_cache()
    assert sesion.quien_es("jwt-del-cockpit").email == "yo@zenvrax.com"
    assert visto == ["/auth/me"]


def test_el_coste_del_scrypt_cabe_en_el_limite_de_openssl():
    """LO ENCONTRO ESTE FICHERO, no el servidor. Con n=2**15 y r=8, scrypt pide 32 MB y OpenSSL trae
    un tope de serie justo ahi: sin declarar `maxmem`, cifrar la clave falla con "memory limit
    exceeded". El primer intento de entrar en produccion habria sido un 500 sin explicacion.

    Se comprueba haciendo la cuenta, no leyendo el codigo: si alguien sube el coste sin subir el
    tope, esto salta antes de desplegarlo.
    """
    pide = 128 * clave_mod._R * clave_mod._N
    assert pide <= clave_mod._MAXMEM, (
        f"scrypt pide {pide // 1024 // 1024} MB y el tope declarado son "
        f"{clave_mod._MAXMEM // 1024 // 1024} MB")
    assert clave_mod.cifra_clave("x").startswith("scrypt$"), "y de verdad se puede cifrar"
