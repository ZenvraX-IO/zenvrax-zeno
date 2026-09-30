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
import threading
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
#: La de LECTURA, que es otra y se usa solo para PREGUNTAR si algo salio. Preguntar no muta nada,
#: asi que no tiene por que ir con la llave que escribe.
CLAVE_LECTURA = os.environ.get("ZENO_READ_KEY", "")
#: Xrise es multi-inquilino y quiere saber de que negocio se le pregunta.
ORG = os.environ.get("ZENO_ORG", "gutlyn")
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
            titulo: str = "", metodo: str = "GET", cuerpo: dict | None = None,
            comprobar: str = "") -> dict:
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
                    "metodo": metodo, "cuerpo": cuerpo, "comprobar": comprobar}
    return {
        "vale": vale, "op": op, "etiqueta": etiqueta, "titulo": titulo,
        "efecto": efecto,
        # Lo que no se deshace se dice ANTES, con todas las letras y no con un icono.
        "sale_al_mundo": efecto == PUBLICA,
        "pide_pin": efecto == PUBLICA,
        "cuesta_dinero": bool(coste_api),
        # La pantalla lo usa para no quedarse esperando: lo que publica se hace en segundo plano.
        "tarda": efecto == PUBLICA,
    }


#: Los encargos que estan saliendo al mundo ahora mismo, por su identificador.
#:
#: POR QUE EXISTEN (2026-09-30). Publicar un post de GutLyn tarda 58,6s medidos, de los cuales 57
#: son la API de Meta (Instagram no deja publicar de una vez: crea un contenedor, espera a que
#: procese la imagen y luego publica) y 0,0s todo el trabajo de n8n. El operador, con la pantalla
#: parada y un aviso de que no se sabia si habia salido: *"tarda mucho en aprobarse y no existe un
#: thick que lo muestre como publicado... se debe comprobar in situ y es algo a evitar"*.
#:
#: El minuto no se puede quitar, pero si se puede no cobrarselo a quien mira.
_ENCARGOS: dict[str, dict] = {}
#: Cuanto se guarda uno ya resuelto: lo justo para que la pantalla lo recoja aunque se cierre Zeno.
_ENCARGO_VIVE = 1800.0

#: Se espera MAS que el sistema de destino (Xrise aguanta 90s al webhook) para que el caso normal
#: termine aqui y no en una comprobacion. Ya no bloquea a nadie: esto corre en segundo plano.
_ESPERA = 120

#: Y cuando ni asi se sabe, se PREGUNTA. Meta puede tardar de mas un dia cargado.
_REINTENTOS, _ENTRE_INTENTOS = 8, 10


def _cabeceras(d: dict) -> dict:
    cab = {"User-Agent": "Zeno/1.0 (asistente del operador)"}
    if d.get("cuerpo") is not None:
        cab["Content-Type"] = "application/json"
    # La clave SOLO a quien tiene que recibirla. Mandarla en cada peticion la entregaria tambien a
    # n8n, que es otro sistema: una credencial no viaja a todo el que aparezca en una url.
    if CLAVE_ESCRITURA and d["url"].startswith(CON_CLAVE):
        cab["X-Zeno-Key"] = CLAVE_ESCRITURA
    return cab


def _url_de_comprobar(d: dict) -> str:
    """La ruta que dice SI SE HIZO: el ultimo tramo de la accion, cambiado por el declarado."""
    if not d.get("comprobar"):
        return ""
    return d["url"].split("?")[0].rsplit("/", 1)[0] + "/" + d["comprobar"]


def pregunta_si_salio(d: dict, espera: int = 20) -> dict | None:
    """Le pregunta al sistema si aquello salio. None si no se puede saber.

    SOLO LEE, y por eso va con la clave de LECTURA: preguntar no muta nada. Si esto fallara, la
    respuesta honesta sigue siendo la duda, nunca un "si" inventado.
    """
    url = _url_de_comprobar(d)
    if not url or not CLAVE_LECTURA:
        return None
    req = urllib.request.Request(url, method="GET", headers={
        "X-Zeno-Key": CLAVE_LECTURA, "X-Zeno-Org": ORG, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=espera) as r:
            return json.loads(r.read() or b"{}")
    except Exception:                                    # noqa: BLE001
        return None


def _dispara(d: dict) -> tuple:
    """La llamada que sale a la red. Devuelve (como_fue, codigo, texto)."""
    datos = json.dumps(d["cuerpo"]).encode() if d.get("cuerpo") is not None else None
    req = urllib.request.Request(d["url"], data=datos, method=d.get("metodo", "GET"),
                                 headers=_cabeceras(d))
    try:
        with urllib.request.urlopen(req, timeout=_ESPERA) as r:
            return "hecho", r.status, (r.read() or b"")[:400].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return "error", e.code, ""
    except Exception as e:                               # noqa: BLE001
        return "no_se_sabe", None, type(e).__name__


def _enlaces(estado: dict) -> dict:
    return {k: estado.get(k) for k in ("ig_url", "fb_url") if estado.get(k)}


def _mensaje(como: str, codigo, texto: str) -> str:
    if como == "hecho":
        return "Publicado"
    if como == "error":
        return (f"el sistema ha contestado {codigo}" if codigo
                else texto or "no se ha podido publicar")
    return ("sigue en marcha y no se ha podido confirmar: NO lo repitas, se comprueba solo")


def _resuelve(encargo: str, d: dict) -> None:
    """Dispara y deja el encargo cerrado. Corre en su propio hilo cuando la accion publica.

    LO QUE NO HACE: repetir la accion. Un timeout DESPUES de mandar la peticion puede significar
    que el post ya salio, asi que reintentar seria publicar dos veces. Se PREGUNTA, que es lo
    unico seguro, y para eso esta `comprobar` en el contrato.
    """
    apunte = {"op": d["op"], "etiqueta": d["etiqueta"], "titulo": d["titulo"],
              "efecto": d["efecto"], "publica": d["efecto"] == PUBLICA}
    como, codigo, texto = _dispara(d)

    # SOLO SE PREGUNTA SI HAY A QUIEN. Sin ruta declarada la duda es honesta y se dice; entrar
    # igual en el bucle serian ochenta segundos durmiendo para acabar diciendo lo mismo.
    if como == "no_se_sabe" and _url_de_comprobar(d) and CLAVE_LECTURA:
        # AQUI ESTABA EL AGUJERO. Antes se rendia con "comprueba en el sistema antes de repetirlo"
        # y mandaba al operador a mirarlo a mano. Si el sistema sabe contestar, se le pregunta.
        for intento in range(_REINTENTOS):
            estado = pregunta_si_salio(d)
            if estado and estado.get("publicado"):
                como, texto = "hecho", "confirmado preguntando al sistema"
                _ENCARGOS[encargo]["enlaces"] = _enlaces(estado)
                break
            if estado and not estado.get("en_marcha"):
                como, texto = "error", "el sistema dice que no llego a publicarse"
                break
            if intento < _REINTENTOS - 1:
                time.sleep(_ENTRE_INTENTOS)

    if como == "hecho" and not _ENCARGOS[encargo].get("enlaces"):
        # Salio bien: se pregunta una vez mas, no para saber si salio sino para traer el enlace al
        # post. Un tic sin enlace obliga a ir a buscarlo, que es lo que se queria evitar.
        estado = pregunta_si_salio(d)
        if estado:
            _ENCARGOS[encargo]["enlaces"] = _enlaces(estado)

    # EL DIARIO VA EN UN try, y no es pereza. Esto se ejecuta DESPUES de que el post haya salido:
    # si escribir el renglon reventara (disco lleno) y se llevara por delante el cierre del
    # encargo, la pantalla se quedaria en "Publicando" para siempre sobre algo que YA se publico, y
    # eso empuja a repetirlo. Un cuaderno que no se puede escribir es un problema; perder la unica
    # senal de que algo salio al mundo es otro mayor.
    #
    # Lo cazo el test que lleva este nombre desde el principio y comprobaba lo contrario que dice:
    # afirmaba "no tumba una accion ya hecha" y exigia `pytest.raises(OSError)`.
    try:
        if como == "hecho":
            diario.apunta({**apunte, "resultado": "hecho", "codigo": codigo or 200})
        elif como == "error":
            diario.apunta({**apunte, "resultado": "error", "codigo": codigo})
        else:
            # SE APUNTA IGUAL, y marcado como dudoso. Un intento del que no se sabe el resultado
            # es justo el que hay que ir a mirar: si no quedara escrito, seria el unico que
            # desaparece del diario.
            # SE GUARDA A QUIEN PREGUNTAR. Sin esto, un apunte dudoso lo es para siempre: el
            # encargo vive en memoria y un reinicio se lo lleva, asi que nadie vuelve a
            # comprobarlo y el historico sigue diciendo "no se sabe" sobre algo que si salio.
            diario.apunta({**apunte, "resultado": "no_se_sabe", "motivo": texto,
                           "url": d.get("url", ""), "comprobar": d.get("comprobar", "")})
    except Exception as e:                               # noqa: BLE001
        # Se deja dicho en el propio encargo: que no quede escrito en el diario es una perdida, y
        # callarla seria peor que el fallo.
        _ENCARGOS[encargo]["sin_apuntar"] = type(e).__name__

    _ENCARGOS[encargo].update(estado=como, codigo=codigo, texto=texto[:200],
                              acabado=time.time(), mensaje=_mensaje(como, codigo, texto))


#: Cuantos dudosos se resuelven de una vez al abrir el historico. Un tope, porque esto son
#: peticiones a otro sistema mientras alguien espera una pantalla.
_DUDOSOS_DE_UNA_VEZ = 4


def resuelve_dudosos(apuntes: list[dict]) -> int:
    """Pregunta por lo que quedo sin saberse y apunta el desenlace. Devuelve cuantos se cerraron.

    EL CASO (2026-09-30). El historico del operador tenia dos lineas del mismo post, una "error" y
    otra "no_se_sabe", y el post habia salido. La segunda se quedo asi porque Zeno se reinicio
    (varios despliegues ese dia) y el encargo, que vive en memoria, se perdio: nadie volvio a mirar.

    NO SE REESCRIBE EL DIARIO, se apunta el desenlace como un renglon mas. El diario es un cuaderno
    de lo que paso, y lo que paso fue un intento dudoso y despues una comprobacion; borrar el
    primero seria perder que hubo dudas. Quien junta los dos es el historico, que se queda con el
    que manda.
    """
    cerrados = 0
    for x in apuntes:
        if cerrados >= _DUDOSOS_DE_UNA_VEZ:
            break
        if x.get("resultado") != "no_se_sabe" or not x.get("comprobar") or not x.get("url"):
            continue
        estado = pregunta_si_salio({"url": x["url"], "comprobar": x["comprobar"]}, espera=8)
        if not estado:
            continue                      # sigue sin saberse: la duda aguanta, no se inventa
        if estado.get("publicado"):
            diario.apunta({**{k: x[k] for k in ("op", "etiqueta", "titulo", "efecto", "publica")
                              if k in x},
                           "resultado": "hecho", "codigo": 200, "resuelto_despues": True})
            cerrados += 1
        elif not estado.get("en_marcha"):
            diario.apunta({**{k: x[k] for k in ("op", "etiqueta", "titulo", "efecto", "publica")
                              if k in x},
                           "resultado": "error", "motivo": "el sistema dice que no salio",
                           "resuelto_despues": True})
            cerrados += 1
    return cerrados


def como_va(encargo: str) -> dict:
    """Como va ese encargo. La pantalla pregunta esto mientras Meta hace lo suyo."""
    ahora = time.time()
    for k, v in list(_ENCARGOS.items()):
        if v.get("acabado") and ahora - v["acabado"] > _ENCARGO_VIVE:
            _ENCARGOS.pop(k, None)
    d = _ENCARGOS.get(encargo)
    if not d:
        # Ni inventar que salio ni decir que fallo: el encargo se perdio (un reinicio), y lo
        # honesto es mandar a recargar la lista, que se lee del sistema y no de aqui.
        raise NoSePuede("ese encargo ya no esta en memoria: recarga la lista para ver como quedo")
    return {"encargo": encargo, "estado": d["estado"], "op": d["op"],
            "etiqueta": d["etiqueta"], "titulo": d["titulo"],
            "mensaje": d.get("mensaje", ""), "enlaces": d.get("enlaces") or {},
            "salio_al_mundo": d["efecto"] == PUBLICA}


def confirma(vale: str, pin_abierto: bool) -> dict:
    """LO UNICO que sale a la red. Sin vale vivo, o sin PIN cuando toca, no hace nada.

    LO QUE PUBLICA NO SE ESPERA AQUI (2026-09-30). Tarda casi un minuto por culpa de Meta y tener
    la pantalla parada no lo acorta: se arranca en segundo plano y se devuelve un encargo que la
    pantalla va preguntando. Lo que solo cambia un estado si se espera, porque es inmediato y asi
    la respuesta ya trae el resultado.
    """
    d = _VALES.get(vale)
    if not d or time.time() - d["nacida"] > _VIVE:
        _VALES.pop(vale, None)
        raise NoSePuede("esa confirmacion ha caducado: vuelve a pedirla")
    if d["efecto"] == PUBLICA and not pin_abierto:
        # Se comprueba ANTES de quemar el vale: si no, un PIN caducado obligaria a rehacer la
        # propuesta cada vez, y eso empuja a dejar el PIN abierto para siempre.
        raise HaceFaltaPin("esta accion publica: hace falta el PIN")

    _VALES.pop(vale, None)          # se quema aqui: a partir de este punto ya no se puede repetir

    encargo = secrets.token_urlsafe(12)
    _ENCARGOS[encargo] = {"estado": "en_marcha", "op": d["op"], "etiqueta": d["etiqueta"],
                          "titulo": d["titulo"], "efecto": d["efecto"], "nacido": time.time(),
                          "enlaces": {}, "mensaje": ""}

    if d["efecto"] != PUBLICA:
        # Cambiar un estado es inmediato: se resuelve aqui y la respuesta ya lo trae hecho.
        _resuelve(encargo, d)
        r = como_va(encargo)
        if r["estado"] != "hecho":
            raise NoSePuede(r["mensaje"])
        return {"hecho": True, "op": d["op"], "etiqueta": d["etiqueta"], "titulo": d["titulo"],
                "encargo": encargo, "codigo": _ENCARGOS[encargo].get("codigo"),
                "salio_al_mundo": False}

    threading.Thread(target=_resuelve, args=(encargo, d), daemon=True,
                     name="zeno-publica-" + encargo).start()
    return {"en_marcha": True, "encargo": encargo, "op": d["op"], "etiqueta": d["etiqueta"],
            "titulo": d["titulo"], "salio_al_mundo": True,
            "aviso": "Publicando en Instagram y Facebook"}
