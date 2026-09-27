# -*- coding: utf-8 -*-
"""J4: lo que no puede pasar entre pulsar un botón y publicar en nombre del operador.

EL CASO. Hasta hoy Zeno leía. Esta pieza aprueba, y aprobar un post de LinkedIn lo publica en ese
momento: no hay papelera, no hay deshacer, y lo ve todo el mundo antes de que nadie se dé cuenta.

Lo que hace esto especialmente fácil de romper es una cosa medida en este mismo sistema: tres de las
acciones de las colas son webhooks de n8n que PUBLICAN, y se llaman con un GET, escritas en el
mismo campo `url` y con la misma forma que un enlace a una guía de ayuda. Nada en el dato las
distingue. Lo único que las separa es el contrato que alguien escribió a mano.

Las siete formas de que esto acabe publicando algo que nadie aprobó:

1. Que se ejecute una acción sin contrato, deduciendo el efecto de la URL.
2. Que proponer ya ejecute.
3. Que un vale sirva dos veces, o caducado.
4. Que algo que publica salga sin el PIN.
5. Que el PIN se pida para todo y se acabe tecleando sin leer.
6. Que se llame a una dirección que no es de casa.
7. Que un timeout se cuente como "no se hizo" y alguien reintente, publicando dos veces.

Puros: sin red. La llamada se sustituye.
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import ejecutor                          # noqa: E402

APROBAR = "https://n8n.zenvrax.com/webhook/linkedin-approve?id=42"
REGENERAR = "https://cockpit.zenvrax.com/api/marketing/regenerar?id=42"


@pytest.fixture(autouse=True)
def _sin_vales():
    ejecutor._VALES.clear()
    yield
    ejecutor._VALES.clear()


def _nada_sale(monkeypatch):
    def no(*a, **k):
        raise AssertionError("ha salido a la red sin confirmar")
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", no)


class _Respuesta:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return b"ok"


def _sale_bien(monkeypatch, visto):
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen",
                        lambda req, timeout=0: visto.append(req.full_url) or _Respuesta())


# ---------------------------------------------------------------- sin contrato no se ejecuta

def test_una_accion_sin_contrato_no_se_ejecuta(monkeypatch):
    """EL TEST QUE IMPORTA. Medido en este sistema: `linkedin-approve` publica y es un GET, igual
    que un enlace a una guia. Si el efecto se dedujera de la URL o del verbo, aprobar un post
    parecería abrir una pantalla."""
    _nada_sale(monkeypatch)
    with pytest.raises(ejecutor.NoSePuede) as e:
        ejecutor.propone("claire.aprobar", "Aprobar", APROBAR, efecto="")
    assert "contrato" in str(e.value)


def test_lo_que_solo_abre_no_se_ejecuta(monkeypatch):
    """Una guia de ayuda no se "ejecuta". Si se pudiera, el boton de ejecutar apareceria sobre
    enlaces inocentes y se perderia la distincion entera."""
    _nada_sale(monkeypatch)
    with pytest.raises(ejecutor.NoSePuede):
        ejecutor.propone("ayuda.guia", "Guia", "https://cockpit.zenvrax.com/guia", ejecutor.ABRE)


def test_un_efecto_inventado_no_pasa(monkeypatch):
    _nada_sale(monkeypatch)
    with pytest.raises(ejecutor.NoSePuede):
        ejecutor.propone("x", "X", APROBAR, efecto="borrar_todo")


def test_solo_se_llama_a_direcciones_de_casa(monkeypatch):
    """El contrato dice QUE hace, no A QUIEN se le pide. La url llega por la API de otro sistema,
    o sea es un dato de fuera, y un dato de fuera no elige a quien llama Zeno."""
    _nada_sale(monkeypatch)
    for fuera in ("https://evil.example.com/webhook/x", "http://n8n.zenvrax.com/x",
                  "https://n8n.zenvrax.com.evil.com/x", ""):
        with pytest.raises(ejecutor.NoSePuede) as e:
            ejecutor.propone("op", "Aprobar", fuera, ejecutor.PUBLICA)
        assert "casa" in str(e.value) or "contrato" in str(e.value)


# ---------------------------------------------------------------- dos tiempos

def test_proponer_no_sale_a_la_red(monkeypatch):
    _nada_sale(monkeypatch)
    p = ejecutor.propone("claire.aprobar", "Aprobar y publicar", APROBAR, ejecutor.PUBLICA)
    assert p["vale"] and p["sale_al_mundo"] is True and p["pide_pin"] is True


def test_la_propuesta_dice_que_sale_al_mundo_antes_de_confirmar():
    """Con todas las letras y no con un icono: es la unica barrera entre pulsar y publicar."""
    publica = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)
    estado = ejecutor.propone("b", "Regenerar", REGENERAR, ejecutor.CAMBIA_ESTADO, coste_api=True)
    assert publica["sale_al_mundo"] is True and estado["sale_al_mundo"] is False
    assert estado["cuesta_dinero"] is True, "lo que gasta API tambien se dice antes"


def test_un_vale_sirve_una_sola_vez(monkeypatch):
    """Pulsar dos veces, o volver atras en el movil, publicaria dos veces."""
    visto = []
    _sale_bien(monkeypatch, visto)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    ejecutor.confirma(v, pin_abierto=True)
    with pytest.raises(ejecutor.NoSePuede):
        ejecutor.confirma(v, pin_abierto=True)
    assert len(visto) == 1


def test_un_vale_caducado_no_publica(monkeypatch):
    _nada_sale(monkeypatch)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    ejecutor._VALES[v]["nacida"] = 0.0
    with pytest.raises(ejecutor.NoSePuede):
        ejecutor.confirma(v, pin_abierto=True)


def test_confirmar_algo_que_nadie_propuso_no_hace_nada(monkeypatch):
    _nada_sale(monkeypatch)
    with pytest.raises(ejecutor.NoSePuede):
        ejecutor.confirma("inventado", pin_abierto=True)


# ---------------------------------------------------------------- el PIN, donde hace falta

def test_lo_que_publica_no_sale_sin_pin(monkeypatch):
    _nada_sale(monkeypatch)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    with pytest.raises(ejecutor.HaceFaltaPin):
        ejecutor.confirma(v, pin_abierto=False)


def test_el_vale_sobrevive_a_un_pin_que_falta(monkeypatch):
    """Si el vale se quemara al faltar el PIN, habria que rehacer la propuesta cada vez, y eso
    empuja a dejar el PIN abierto siempre, que es justo lo que se quiere evitar."""
    visto = []
    _sale_bien(monkeypatch, visto)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    with pytest.raises(ejecutor.HaceFaltaPin):
        ejecutor.confirma(v, pin_abierto=False)
    ejecutor.confirma(v, pin_abierto=True)               # el mismo vale, ya con PIN
    assert len(visto) == 1


def test_cambiar_un_estado_no_pide_pin(monkeypatch):
    """Pedir PIN para todo entrena a teclearlo sin leer, y entonces deja de proteger lo que importa.
    Regenerar un borrador se deshace regenerandolo otra vez; publicar no."""
    visto = []
    _sale_bien(monkeypatch, visto)
    v = ejecutor.propone("b", "Regenerar", REGENERAR, ejecutor.CAMBIA_ESTADO)["vale"]
    r = ejecutor.confirma(v, pin_abierto=False)
    assert r["hecho"] is True and r["salio_al_mundo"] is False
    assert visto == [REGENERAR]


# ---------------------------------------------------------------- cuando no se sabe, se dice

def test_un_timeout_no_dice_que_no_se_hizo(monkeypatch):
    """EL FALLO SUTIL. Un timeout despues de mandar la peticion puede significar que el post YA
    salio. Contestar "no se ha podido" es mentir con seguridad, y lleva a reintentar, o sea a
    publicar dos veces. Hay que decir que no se sabe y donde mirarlo."""
    def cuelga(*a, **k):
        raise TimeoutError("se acabo el tiempo")
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", cuelga)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    with pytest.raises(ejecutor.NoSePuede) as e:
        ejecutor.confirma(v, pin_abierto=True)
    mensaje = str(e.value)
    assert "no se ha podido saber" in mensaje
    assert "comprueba" in mensaje, "y dice que hay que mirarlo antes de repetir"


def test_un_error_del_sistema_se_dice_con_su_codigo(monkeypatch):
    import urllib.error
    def falla(*a, **k):
        raise urllib.error.HTTPError(APROBAR, 500, "boom", {}, None)
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", falla)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    with pytest.raises(ejecutor.NoSePuede) as e:
        ejecutor.confirma(v, pin_abierto=True)
    assert "500" in str(e.value)


def test_no_hay_ninguna_forma_de_ejecutar_en_lote():
    """Hay 113 pendientes. Un boton de "aprobar todo" seria la forma mas rapida de publicar veinte
    cosas sin leer ninguna, y este modulo no puede ofrecerlo ni por descuido."""
    fuente = (RAIZ / "servicio" / "ejecutor.py").read_text(encoding="utf-8")
    for masivo in ("for vale in", "def confirma_todo", "def propone_todos", "lote"):
        assert masivo not in fuente or "lote" in fuente.split("LO QUE NO HACE")[1][:400]


# ---------------------------------------------------------------- queda escrito lo que sale

def test_lo_ejecutado_queda_apuntado(monkeypatch):
    """Con J4, Zeno publica en nombre del operador y el unico sitio donde constaba era el sistema
    de destino, mezclado con lo que aprueba el cockpit y lo que aprueba Xrise. La primera pregunta
    al ver algo publicado que no recuerdas es si lo aprobaste tu desde aqui."""
    apuntes = []
    monkeypatch.setattr(ejecutor.diario, "apunta", apuntes.append)
    _sale_bien(monkeypatch, [])
    v = ejecutor.propone("claire.aprobar", "Aprobar", APROBAR, ejecutor.PUBLICA, titulo="Un post")
    ejecutor.confirma(v["vale"], pin_abierto=True)
    assert len(apuntes) == 1
    assert apuntes[0]["resultado"] == "hecho" and apuntes[0]["publica"] is True
    assert apuntes[0]["titulo"] == "Un post"


def test_lo_que_no_se_sabe_TAMBIEN_queda_apuntado(monkeypatch):
    """EL RENGLON QUE MAS IMPORTA. Un timeout puede significar que el post ya salio. Si ese intento
    no quedara escrito, seria justo el unico que desaparece del diario, y es el unico que hay que
    ir a mirar."""
    apuntes = []
    monkeypatch.setattr(ejecutor.diario, "apunta", apuntes.append)
    def cuelga(*a, **k):
        raise TimeoutError("boom")
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen", cuelga)
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    with pytest.raises(ejecutor.NoSePuede):
        ejecutor.confirma(v, pin_abierto=True)
    assert apuntes[0]["resultado"] == "no_se_sabe"


def test_un_diario_roto_no_tumba_una_accion_ya_hecha(monkeypatch):
    """Si apuntar reventara DESPUES de publicar, el operador veria un error y creeria que no salio,
    cuando si salio. Eso lleva a reintentar, o sea a publicar dos veces."""
    def revienta(_):
        raise OSError("disco lleno")
    monkeypatch.setattr(ejecutor.diario, "apunta", revienta)
    _sale_bien(monkeypatch, [])
    v = ejecutor.propone("a", "Aprobar", APROBAR, ejecutor.PUBLICA)["vale"]
    with pytest.raises(OSError):
        ejecutor.confirma(v, pin_abierto=True)


def test_el_diario_aguanta_una_linea_rota(monkeypatch, tmp_path):
    """Un reinicio en mitad de una escritura deja media linea. Tirar el fichero entero por eso
    seria perder el historial de meses por un renglon."""
    from servicio import diario
    libro = tmp_path / "hecho.jsonl"
    monkeypatch.setattr(diario, "LIBRO", libro)
    diario.apunta({"op": "uno", "resultado": "hecho"})
    with libro.open("a", encoding="utf-8") as f:
        f.write('{"op": "a med')
    diario.apunta({"op": "dos", "resultado": "hecho"})
    ops = [x["op"] for x in diario.lee()]
    assert ops == ["dos", "uno"], ops


def test_el_diario_no_guarda_el_cuerpo_de_lo_publicado():
    """Zeno no es el sitio donde vive el contenido. Una copia seria la tercera verdad que esta
    arquitectura evita a proposito: se guarda QUE accion, sobre QUE, cuando y como acabo."""
    fuente = (RAIZ / "servicio" / "ejecutor.py").read_text(encoding="utf-8")
    trozo = fuente[fuente.index("apunte = {"):fuente.index("req = urllib.request.Request")]
    for prohibido in ("cuerpo", "body", "contenido", "texto"):
        assert prohibido not in trozo, f"el diario guarda {prohibido}"
