# -*- coding: utf-8 -*-
"""El histórico cuenta cosas, no intentos, y lo que quedó en duda se resuelve solo.

EL CASO (2026-09-30). El operador: *"existen duplicados en Zeno. No debería ser de esa manera.
Míralo porque los duplicados no deberían estar"*. Medido ese día en las dos colas, el correo, los
apuntes, los avisos y la agenda, todo limpio menos una cosa, su histórico de "Hoy has hecho":

    Aprobar y publicar | W5/P16 D35 - Loading: skip it | no_se_sabe
    Aprobar y publicar | W5/P16 D35 - Loading: skip it | error

Dos líneas para UN post, y las dos falsas: el post SÍ salió (Instagram y Facebook, 12:44:01). Eran
los dos intentos de ese día, el que se llevó un 401 porque la llave de Zeno no llegaba a Xrise, y
el que se agotó a los 45 segundos mientras Instagram procesaba la imagen.

TRES COSAS DISTINTAS, y conviene no mezclarlas:

  1. El diario apunta INTENTOS, y eso está bien: si el intento fallido no quedara escrito,
     desaparecería justo el que hay que mirar.
  2. Lo que NO puede es subir a la pantalla tal cual. "Hoy has hecho 4 cosas" contando dos intentos
     del mismo post cuenta mal, y repetir la tarjeta de algo que no se deshace se lee como que se
     publicó dos veces, que es el susto que hay que evitar.
  3. Y un apunte dudoso que nadie vuelve a mirar miente para siempre. El encargo vive en memoria y
     un reinicio se lo lleva, así que la duda se resuelve al abrir el histórico, preguntando.
"""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from servicio import api, ejecutor  # noqa: E402

AHORA = time.time()


def _ap(etiqueta, titulo, resultado, cuando=0.0, **extra):
    return {"op": "gutlyn.aprobar_y_publicar", "etiqueta": etiqueta, "titulo": titulo,
            "efecto": "publica", "publica": True, "resultado": resultado,
            "cuando": cuando or AHORA, **extra}


# ------------------------------------------------------------------ 1. una línea por cosa

def test_dos_intentos_del_mismo_post_son_UNA_linea():
    """EL DUPLICADO QUE VIO EL OPERADOR, tal cual estaba en su histórico."""
    fuera = api._una_linea_por_cosa([
        _ap("Aprobar y publicar", "W5/P16 D35 - Loading: skip it", "no_se_sabe", AHORA - 10),
        _ap("Aprobar y publicar", "W5/P16 D35 - Loading: skip it", "error", AHORA - 90),
    ])
    assert len(fuera) == 1, f"siguen saliendo {len(fuera)} tarjetas del mismo post"
    assert fuera[0]["intentos"] == 2, "se ha perdido que hubo dos intentos"


def test_un_exito_MANDA_sobre_los_fallos_anteriores():
    """Si el post acabó publicado, el día no tiene un error: tiene una publicación. Enseñar el
    fallo sería mandar al operador a mirar algo que ya está resuelto."""
    fuera = api._una_linea_por_cosa([
        _ap("Aprobar y publicar", "Un post", "error", AHORA - 200),
        _ap("Aprobar y publicar", "Un post", "hecho", AHORA - 5),
        _ap("Aprobar y publicar", "Un post", "no_se_sabe", AHORA - 100),
    ])
    assert len(fuera) == 1 and fuera[0]["resultado"] == "hecho"
    assert fuera[0]["intentos"] == 3


def test_la_duda_manda_sobre_el_error():
    """Y el orden importa en el otro sentido: entre un error y una duda gana la duda, porque la
    duda es la que hay que ir a mirar. Un error da el asunto por cerrado."""
    fuera = api._una_linea_por_cosa([
        _ap("Aprobar y publicar", "Un post", "error", AHORA - 200),
        _ap("Aprobar y publicar", "Un post", "no_se_sabe", AHORA - 5),
    ])
    assert fuera[0]["resultado"] == "no_se_sabe"


def test_dos_posts_distintos_NO_se_juntan():
    """Lo que no puede pasar: que agrupar se coma trabajo de verdad. Dos posts con la misma
    etiqueta son dos cosas, y contarlos como una escondería uno."""
    fuera = api._una_linea_por_cosa([
        _ap("Aprobar y publicar", "Post A", "hecho"),
        _ap("Aprobar y publicar", "Post B", "hecho"),
    ])
    assert len(fuera) == 2, "ha juntado dos posts distintos"


def test_lo_que_no_tiene_titulo_no_se_junta_a_ciegas():
    """Sin título no hay forma de saber si son la misma cosa. Antes juntarlos que esconder uno."""
    fuera = api._una_linea_por_cosa([
        _ap("Saltar hoy", "", "hecho"), _ap("Saltar hoy", "", "hecho"),
    ])
    assert len(fuera) == 2


def test_se_queda_la_hora_del_ULTIMO_intento():
    """La cosa acaba cuando acaba el último intento, no cuando empezó el primero."""
    fuera = api._una_linea_por_cosa([
        _ap("Aprobar y publicar", "Un post", "error", AHORA - 500),
        _ap("Aprobar y publicar", "Un post", "hecho", AHORA - 5),
    ])
    assert fuera[0]["cuando"] == AHORA - 5


def test_el_orden_sigue_siendo_lo_mas_reciente_primero():
    fuera = api._una_linea_por_cosa([
        _ap("Aprobar", "Viejo", "hecho", AHORA - 900),
        _ap("Aprobar", "Nuevo", "hecho", AHORA - 10),
    ])
    assert [x["titulo"] for x in fuera] == ["Nuevo", "Viejo"]


# ------------------------------------------------------------------ 2. la duda se resuelve sola

def test_un_apunte_dudoso_se_cierra_preguntando(monkeypatch):
    """LO QUE DEJABA EL HISTORICO MINTIENDO. El encargo vive en memoria y un reinicio se lo lleva;
    si nadie vuelve a preguntar, el apunte dice "no se sabe" para siempre sobre algo que salió."""
    apuntados = []
    monkeypatch.setattr(ejecutor.diario, "apunta", apuntados.append)
    monkeypatch.setattr(ejecutor, "pregunta_si_salio", lambda d, espera=8: {"publicado": True})
    dudoso = _ap("Aprobar y publicar", "Un post", "no_se_sabe",
                 url="http://ecomops-api:8803/content/gutlyn/abc/action", comprobar="estado")
    assert ejecutor.resuelve_dudosos([dudoso]) == 1
    assert apuntados[0]["resultado"] == "hecho" and apuntados[0]["resuelto_despues"] is True


def test_si_sigue_sin_saberse_NO_se_inventa(monkeypatch):
    """Lo peor que podría hacer esto es cerrar en falso. Si el sistema no contesta, la duda aguanta."""
    apuntados = []
    monkeypatch.setattr(ejecutor.diario, "apunta", apuntados.append)
    monkeypatch.setattr(ejecutor, "pregunta_si_salio", lambda d, espera=8: None)
    dudoso = _ap("Aprobar y publicar", "Un post", "no_se_sabe",
                 url="http://ecomops-api:8803/content/gutlyn/abc/action", comprobar="estado")
    assert ejecutor.resuelve_dudosos([dudoso]) == 0
    assert apuntados == []


def test_sin_a_quien_preguntar_no_se_toca(monkeypatch):
    """Un apunte viejo, escrito antes de que se guardara la url, no se puede resolver. Y no pasa
    nada: lo que no se puede saber se sigue diciendo."""
    def no_deberia(*a, **k):
        raise AssertionError("ha preguntado sin tener a quien")
    monkeypatch.setattr(ejecutor, "pregunta_si_salio", no_deberia)
    assert ejecutor.resuelve_dudosos([_ap("Aprobar y publicar", "Un post", "no_se_sabe")]) == 0


def test_resolver_NO_vuelve_a_disparar_la_accion(monkeypatch):
    """LA LÍNEA QUE NO SE CRUZA. Resolver una duda es preguntar, nunca repetir: el post pudo salir,
    y repetirlo lo publicaría dos veces."""
    disparos = []
    monkeypatch.setattr(ejecutor.diario, "apunta", lambda x: None)
    monkeypatch.setattr(ejecutor.urllib.request, "urlopen",
                        lambda req, *a, **k: disparos.append(getattr(req, "method", "?")))
    monkeypatch.setattr(ejecutor, "pregunta_si_salio", lambda d, espera=8: {"publicado": True})
    ejecutor.resuelve_dudosos([_ap("Aprobar y publicar", "Un post", "no_se_sabe",
                                   url="http://ecomops-api:8803/content/gutlyn/abc/action",
                                   comprobar="estado")])
    assert disparos == [], f"ha vuelto a disparar algo: {disparos}"


def test_hay_un_tope_de_consultas(monkeypatch):
    """Esto son peticiones a otro sistema mientras alguien espera una pantalla. Sin tope, un día
    con veinte dudosos dejaría el histórico colgado."""
    monkeypatch.setattr(ejecutor.diario, "apunta", lambda x: None)
    veces = []
    monkeypatch.setattr(ejecutor, "pregunta_si_salio",
                        lambda d, espera=8: veces.append(1) or {"publicado": True})
    muchos = [_ap("Aprobar y publicar", f"Post {i}", "no_se_sabe",
                  url=f"http://ecomops-api:8803/content/gutlyn/{i}/action", comprobar="estado")
              for i in range(20)]
    ejecutor.resuelve_dudosos(muchos)
    assert len(veces) <= ejecutor._DUDOSOS_DE_UNA_VEZ


def test_el_apunte_dudoso_guarda_a_quien_preguntar():
    """Si el apunte no guardara la url, nada de lo de arriba serviría en producción: el histórico
    no tendría a quién preguntar y la duda quedaría para siempre."""
    fuente = (RAIZ / "servicio" / "ejecutor.py").read_text(encoding="utf-8")
    i = fuente.index('"resultado": "no_se_sabe"')
    assert '"url": d.get("url"' in fuente[i:i + 300], "el apunte dudoso no guarda la url"
    assert '"comprobar": d.get("comprobar"' in fuente[i:i + 300]


# ------------------------------------------------------------------ 3. el ENDPOINT, no la pieza
#
# LOS DOS FALLOS QUE SE ESCAPARON. Probando el saboteador, "no agrupar" y "no resolver las dudas"
# PASABAN: todo lo de arriba llama a `_una_linea_por_cosa` y a `resuelve_dudosos` directamente, y
# ninguno pasaba por `/api/hecho`, que es lo que pinta la pantalla. Se puede dejar la funcion
# perfecta y no llamarla, que es exactamente el fallo que tenia el sistema antes de hoy.

def _hecho(monkeypatch, apuntes, resuelve=lambda a: 0):
    import asyncio
    monkeypatch.setattr(api, "_quien", lambda *a, **k: ("yo", "t"))
    monkeypatch.setattr(api.diario, "de_hoy", lambda: apuntes)
    monkeypatch.setattr(api.ejecutor, "resuelve_dudosos", resuelve)
    return asyncio.run(api.api_hecho(authorization="Bearer x"))


def test_EL_ENDPOINT_no_devuelve_la_misma_cosa_dos_veces(monkeypatch):
    """LA TARJETA REPETIDA QUE VIO EL OPERADOR, pedida por donde la pide la pantalla."""
    r = _hecho(monkeypatch, [
        _ap("Aprobar y publicar", "W5/P16 D35 - Loading: skip it", "no_se_sabe", AHORA - 10),
        _ap("Aprobar y publicar", "W5/P16 D35 - Loading: skip it", "error", AHORA - 90),
        _ap("Mensaje enviado", "Paola Martínez Pardo", "hecho", AHORA - 300),
    ])
    assert len(r["hecho"]) == 2, f"la pantalla sigue recibiendo {len(r['hecho'])} tarjetas"
    assert r["cuantas"] == 2, "sigue contando intentos y no cosas: dira 'has hecho 3'"
    cuantas = {x["que"]: x["cuantas"] for x in r["resumen"]}
    assert cuantas["Aprobar y publicar"] == 1, cuantas


def test_EL_ENDPOINT_resuelve_las_dudas_antes_de_enseñarlas(monkeypatch):
    """Y las resuelve de verdad: si solo se llamara a la funcion sin releer, el historico
    enseñaria la duda vieja aunque acabara de cerrarse."""
    llamado = []
    dudoso = _ap("Aprobar y publicar", "Un post", "no_se_sabe", AHORA - 10,
                 url="http://ecomops-api:8803/content/gutlyn/abc/action", comprobar="estado")
    ya = _ap("Aprobar y publicar", "Un post", "hecho", AHORA - 1)

    # La primera lectura trae la duda; tras resolverla, el diario ya tiene el desenlace.
    lecturas = [[dudoso], [dudoso, ya]]
    import asyncio
    monkeypatch.setattr(api, "_quien", lambda *a, **k: ("yo", "t"))
    monkeypatch.setattr(api.diario, "de_hoy", lambda: lecturas.pop(0) if lecturas else [dudoso, ya])
    monkeypatch.setattr(api.ejecutor, "resuelve_dudosos", lambda a: llamado.append(a) or 1)
    r = asyncio.run(api.api_hecho(authorization="Bearer x"))

    assert llamado, "el historico no intenta resolver lo que quedo en duda"
    assert len(r["hecho"]) == 1 and r["hecho"][0]["resultado"] == "hecho", (
        "no ha releido el diario: enseña la duda que acaba de cerrarse")
    assert r["dudosas"] == 0
