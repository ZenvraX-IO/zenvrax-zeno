# -*- coding: utf-8 -*-
"""J4: ejecutar una acción de las colas desde Zeno. La fase que rompe la promesa de no tocar nada.

HASTA HOY Zeno leía y enlazaba. Enseñaba 113 cosas pendientes y para aprobar cualquiera había que
irse al cockpit o a Xrise. Esto lo cierra, y es el cambio con más consecuencias de todo el proyecto:
aprobar un post de LinkedIn lo publica en ese momento, en nombre del operador, y no se deshace.

LAS CUATRO BARRERAS, y ninguna sobra:

  1. **El contrato manda, no la URL.** Cada acción viene del catálogo con su `efecto` declarado a
     mano. No se deduce del verbo ni del dominio: tres acciones de las colas son webhooks de n8n que
     PUBLICAN y se llaman con un GET, escritas exactamente igual que un enlace a una guía de ayuda.
     Si una acción llega sin contrato, no se ejecuta.
  2. **Dos tiempos.** `propone` calcula y devuelve un vale; `confirma` es lo único que sale a la
     red. Mismo patrón que la agenda, que ya está rodado.
  3. **PIN para lo irreversible.** Lo que publica pide la segunda llave. Lo que solo cambia un
     estado, no: pedir PIN para todo entrena a teclearlo sin leer, y entonces deja de proteger.
  4. **Un vale, una vez.** Pulsar dos veces publicaría dos veces.

LO QUE NO HACE, a propósito: no ejecuta nada en lote. Hay 113 pendientes y un botón de "aprobar
todo" sería la forma más rápida de publicar veinte cosas sin leer ninguna.
"""
from __future__ import annotations

import os
import secrets
import time
import json
import urllib.error
import urllib.request

from servicio import diario

#: Los tres efectos que declara el catalogo. Se repiten aqui como constantes para que este modulo
#: no dependa de importar el catalogo entero, que dentro del contenedor vive congelado.
PUBLICA = "publica"
CAMBIA_ESTADO = "cambia_estado"
ABRE = "abre"

#: A donde se permite llamar. Una accion cuya URL no sea de casa NO se ejecuta, aunque traiga
#: contrato: el contrato dice que hace, no a quien se lo pide, y una URL que llega por la API de
#: otro sistema es un dato de fuera.
CASAS = tuple(x.strip() for x in os.environ.get(
    "ZENO_CASAS",
    "https://n8n.zenvrax.com/,https://cockpit.zenvrax.com/,https://xrise.zenvrax.com/,"
    "http://cockpit-api:8802/,http://ecomops-api:8803/"
).split(",") if x.strip())

#: LA CLAVE DE ESCRITURA, y a QUIEN se le manda. Solo viaja a las direcciones de la API de casa:
#: mandarla en cada peticion la entregaria tambien a n8n, que es otro sistema y no la necesita.
#: Una credencial se manda a quien tiene que recibirla, no a todo el que aparezca en una url.
#: VAN LOS DOS SISTEMAS, y Xrise faltaba. El 30-sep el operador pulso Publicar en un post de
#: GutLyn y se llevo un 401: la puerta de Xrise permitia `publish` desde el 28-sep, pero esta lista
#: solo nombraba al cockpit, asi que la llamada salia sin cabecera. Ninguna accion de GutLyn habia
#: funcionado nunca, y no se noto porque las del cockpit si. Lo guarda
#: tests/test_la_clave_llega_a_todos_los_sistemas.py, que lo deriva de los ZENO_*_URL del compose
#: en vez de repetir la lista a mano.
CLAVE_ESCRITURA = os.environ.get("ZENO_WRITE_KEY", "")
CON_CLAVE = tuple(x.strip() for x in os.environ.get(
    "ZENO_CON_CLAVE",
    "http://cockpit-api:8802/,https://cockpit.zenvrax.com/api/,"
    "http://ecomops-api:8803/,https://xrise.zenvrax.com/api/"
).split(",") if x.strip())

_VALES: dict[str, dict] = {}
_VIVE = 300.0                 # cinco minutos: menos que la agenda, porque esto no se deshace


class NoSePuede(RuntimeError):
    """La accion no se puede ejecutar, y el mensaje dice por que."""


class HaceFaltaPin(RuntimeError):
    """Esta accion publica y la sesion no ha puesto el PIN."""


def _de_casa(url: str) -> bool:
    return bool(url) and url.startswith(CASAS)


#: Los verbos que se admiten. GET para los webhooks de las colas (asi estan hechos) y PATCH para
#: cambiar un estado. DELETE no esta: borrar no se pidio y no se abre "por si acaso".
METODOS = ("GET", "PATCH", "POST")


def propone(op: str, etiqueta: str, url: str, efecto: str, coste_api: bool = False,
            titulo: str = "", metodo: str = "GET", cuerpo: dict | None = None) -> dict:
    """Prepara una ejecucion y devuelve un vale. NO llama a nadie."""
    if not op or not efecto:
        # Sin contrato no se ejecuta. El recolector del catalogo ya se niega a inventarlo, y aqui
        # se vuelve a comprobar: entre el catalogo y este punto hay una API y un navegador.
        raise NoSePuede("esa accion no trae contrato, y sin contrato no se ejecuta")
    if efecto == ABRE:
        raise NoSePuede("esa accion solo abre una pantalla: no hay nada que ejecutar")
    if efecto not in (PUBLICA, CAMBIA_ESTADO):
        raise NoSePuede(f"efecto desconocido: {efecto}")
    if not _de_casa(url):
        raise NoSePuede("esa direccion no es de ninguno de los sistemas de casa")
    metodo = (metodo or "GET").upper()
    if metodo not in METODOS:
        raise NoSePuede(f"metodo no permitido: {metodo}")

    ahora = time.time()
    for v, d in list(_VALES.items()):
        if ahora - d["nacida"] > _VIVE:
            _VALES.pop(v, None)
    vale = secrets.token_urlsafe(18)
    _VALES[vale] = {"nacida": ahora, "op": op, "url": url, "efecto": efecto,
                    "etiqueta": etiqueta, "coste_api": coste_api, "titulo": titulo,
                    "metodo": metodo, "cuerpo": cuerpo}
    return {
        "vale": vale, "op": op, "etiqueta": etiqueta, "titulo": titulo,
        "efecto": efecto,
        # Lo que no se deshace se dice ANTES, con todas las letras y no con un icono.
        "sale_al_mundo": efecto == PUBLICA,
        "pide_pin": efecto == PUBLICA,
        "cuesta_dinero": bool(coste_api),
    }


def confirma(vale: str, pin_abierto: bool) -> dict:
    """LO UNICO que sale a la red. Sin vale vivo, o sin PIN cuando toca, no hace nada."""
    d = _VALES.get(vale)
    if not d or time.time() - d["nacida"] > _VIVE:
        _VALES.pop(vale, None)
        raise NoSePuede("esa confirmacion ha caducado: vuelve a pedirla")
    if d["efecto"] == PUBLICA and not pin_abierto:
        # Se comprueba ANTES de quemar el vale: si no, un PIN caducado obligaria a rehacer la
        # propuesta cada vez, y eso empuja a dejar el PIN abierto para siempre.
        raise HaceFaltaPin("esta accion publica: hace falta el PIN")

    _VALES.pop(vale, None)          # se quema aqui: a partir de este punto ya no se puede repetir
    apunte = {"op": d["op"], "etiqueta": d["etiqueta"], "titulo": d["titulo"],
              "efecto": d["efecto"], "publica": d["efecto"] == PUBLICA}
    cabeceras = {
        # Que se sepa desde donde se disparo. Si un post sale raro, el primer dato util es si lo
        # aprobo el cockpit, Xrise o Zeno.
        "User-Agent": "Zeno/1.0 (asistente del operador)"}
    datos = None
    if d.get("cuerpo") is not None:
        datos = json.dumps(d["cuerpo"]).encode()
        cabeceras["Content-Type"] = "application/json"
    # La clave SOLO a quien tiene que recibirla. Mandarla en cada peticion la entregaria tambien a
    # n8n, que es otro sistema: una credencial no viaja a todo el que aparezca en una url.
    if CLAVE_ESCRITURA and d["url"].startswith(CON_CLAVE):
        cabeceras["X-Zeno-Key"] = CLAVE_ESCRITURA
    req = urllib.request.Request(d["url"], data=datos, method=d.get("metodo", "GET"),
                                 headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            cuerpo = (r.read() or b"")[:400].decode("utf-8", "replace")
            codigo = r.status
    except urllib.error.HTTPError as e:
        diario.apunta({**apunte, "resultado": "error", "codigo": e.code})
        raise NoSePuede(f"el sistema ha contestado {e.code}") from e
    except Exception as e:                               # noqa: BLE001
        # AQUI NO SE SABE SI SE HIZO. Un timeout despues de mandar la peticion puede significar que
        # el post ya salio. Decir "no se ha podido" seria mentir con seguridad y llevaria a
        # reintentar, o sea a publicar dos veces.
        # SE APUNTA IGUAL, y marcado como dudoso. Un intento del que no se sabe el resultado es
        # justo el que hay que ir a mirar: si no quedara escrito, seria el unico que desaparece.
        diario.apunta({**apunte, "resultado": "no_se_sabe", "motivo": type(e).__name__})
        raise NoSePuede(
            f"no se ha podido saber si salio ({type(e).__name__}): comprueba en el sistema antes "
            "de repetirlo") from e

    diario.apunta({**apunte, "resultado": "hecho", "codigo": codigo})
    return {"hecho": True, "op": d["op"], "etiqueta": d["etiqueta"], "titulo": d["titulo"],
            "codigo": codigo, "respuesta": cuerpo.strip()[:200],
            "salio_al_mundo": d["efecto"] == PUBLICA}
