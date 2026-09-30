# -*- coding: utf-8 -*-
"""La clave de escritura llega a TODOS los sistemas a los que Zeno dispara acciones.

EL CASO (2026-09-30). El operador pulsó Publicar en un post de GutLyn y la pantalla dijo *"el
sistema ha contestado 401"*. Medido en los registros, al milisegundo:

    12:21:10.752  Zeno → PIN con la cara                            200
    12:21:10.833  Zeno → Xrise /content/gutlyn/{uuid}/action        401
    12:21:10.834  Zeno → la pantalla                                409

LA PUERTA ESTABA BIEN Y LA LLAVE NO SALIÓ. `core/puerta_zeno.py` de Xrise permitía `publish` en
`gutlyn` desde el 28-sep, con sus tests; si hubiera sido la puerta el código habría sido 403. Fue
401: Zeno llamó SIN la cabecera `X-Zeno-Key`, porque `ZENO_CON_CLAVE` solo listaba el cockpit.

Consecuencia: NINGUNA acción de GutLyn funcionó nunca desde Zeno. Las del cockpit sí, y eso es lo
que lo mantuvo invisible dos días.

POR QUÉ ESTE TEST NO ES OTRA LISTA A MANO. La lista de al lado, `ZENO_CASAS`, ya sufrió este mismo
fallo (su comentario en el compose lo cuenta: *"el default del codigo si las tenia, y esta linea lo
pisaba en silencio"*). Escribir aquí "cockpit y xrise" repetiría el error a la tercera. Lo que se
comprueba es DERIVADO: cada sistema que el ejecutor tiene declarado con su `ZENO_*_URL` tiene que
estar cubierto por `ZENO_CON_CLAVE`, en el código y en el compose. Un sistema nuevo mañana entra
solo en la comprobación.

n8n queda fuera a propósito y por eso la comprobación es sobre los `ZENO_*_URL`: n8n es de casa
(está en `ZENO_CASAS`) pero no tiene una URL de sistema declarada porque Zeno no le manda la clave.
"""
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

COMPOSE = (RAIZ / "infra" / "docker-compose.zeno.yml").read_text(encoding="utf-8")


def _del_compose(nombre: str) -> str:
    """El valor que el compose entrega, con su `${VAR:-default}` ya resuelto al default."""
    m = re.search(rf"^\s*{nombre}:\s*(.+?)\s*$", COMPOSE, re.M)
    assert m, f"{nombre} no está en el compose de Zeno"
    v = m.group(1)
    d = re.fullmatch(r"\$\{[A-Z_]+:-(.*)\}", v)
    return d.group(1) if d else v


def _cubre(lista: tuple[str, ...], url: str) -> bool:
    """Si alguna entrada de la lista es prefijo de esa url. `startswith` es lo que usa el ejecutor,
    así que se comprueba igual y no con una comparación parecida."""
    return (url.rstrip("/") + "/").startswith(tuple(lista))


#: Los sistemas a los que Zeno dispara acciones, leídos del compose y no escritos aquí.
SISTEMAS = {n: _del_compose(n) for n in re.findall(r"^\s*(ZENO_\w+_URL):", COMPOSE, re.M)
            if n != "ZENO_URL_PUBLICA"}


def test_hay_sistemas_que_comprobar():
    """Si el patrón dejara de encontrar nada, todo lo de abajo pasaría en vacío y el guardián se
    volvería decorativo. Ya pasó con otros: contaban cero y decían ok."""
    assert len(SISTEMAS) >= 2, f"solo encuentro {SISTEMAS}: el guardián no está mirando nada"
    assert "ZENO_XRISE_URL" in SISTEMAS, "falta Xrise, que es donde vive GutLyn"


def test_el_codigo_manda_la_clave_a_todos_los_sistemas():
    """EL FALLO DEL 30-SEP. El default del código dejaba fuera a Xrise."""
    from servicio import ejecutor

    fuera = [f"{n} ({u})" for n, u in SISTEMAS.items() if not _cubre(ejecutor.CON_CLAVE, u)]
    assert not fuera, (
        f"el ejecutor NO manda la clave a {fuera}: esas llamadas contestan 401.\n"
        f"CON_CLAVE es {ejecutor.CON_CLAVE}")


def test_el_compose_manda_la_clave_a_todos_los_sistemas():
    """El otro lado, y el que de verdad manda en producción: el compose PISA al default del código,
    así que arreglar solo el código dejaría el 401 puesto."""
    con_clave = tuple(x.strip() for x in _del_compose("ZENO_CON_CLAVE").split(",") if x.strip())
    fuera = [f"{n} ({u})" for n, u in SISTEMAS.items() if not _cubre(con_clave, u)]
    assert not fuera, f"el compose no manda la clave a {fuera}"


def test_el_codigo_y_el_compose_dicen_LO_MISMO():
    """La forma en que este fallo entra: alguien arregla uno de los dos. Con los dos defaults
    iguales, leer cualquiera de ellos dice la verdad."""
    from servicio import ejecutor

    for nombre, enel_codigo in (("ZENO_CON_CLAVE", ejecutor.CON_CLAVE),
                                ("ZENO_CASAS", ejecutor.CASAS)):
        # El entorno de los tests no define estas variables, así que `enel_codigo` es el default.
        assert not os.environ.get(nombre), f"{nombre} está en el entorno: este test mediría eso"
        del_compose = tuple(x.strip() for x in _del_compose(nombre).split(",") if x.strip())
        assert set(del_compose) == set(enel_codigo), (
            f"{nombre} difiere.\n  compose: {sorted(del_compose)}\n  código:  "
            f"{sorted(enel_codigo)}")


def test_la_clave_no_viaja_a_n8n():
    """Y el límite, que es la razón de que esta lista exista en vez de mandarla siempre: n8n es de
    casa, no necesita la clave y no se le manda. Si esto cayera, el arreglo del 401 se habría hecho
    abriendo la mano en vez de nombrando a Xrise."""
    from servicio import ejecutor

    assert _cubre(ejecutor.CASAS, "https://n8n.zenvrax.com/webhook/x"), "n8n debería ser de casa"
    assert not _cubre(ejecutor.CON_CLAVE, "https://n8n.zenvrax.com/webhook/x"), (
        "la clave de escritura viaja a n8n, que es otro sistema y no la necesita")
