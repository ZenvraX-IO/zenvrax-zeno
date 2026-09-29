# -*- coding: utf-8 -*-
"""El correo y la agenda del operador. SOLO LECTURA, y sin guardar nada.

UN BUZON PUEDE TENER VARIOS NOMBRES, y eso rompió el diseño inicial. Se dio por hecho que
`ghidalgo@zenvrax.com` y `ghidalgo@gutlyn.com` eran dos cuentas de Google separadas, porque son dos
dominios y los dos tienen Workspace. Medido el 2026-09-27 preguntándole a Google: **son el mismo
buzón**, 498 mensajes y el mismo `historyId` en las dos autorizaciones. El segundo es un alias.

Leer "las dos" era entonces leer dos veces lo mismo, y cada correo salía duplicado en la pantalla.
Así que ahora:

  · Cada buzón se lee UNA vez, aunque tenga dos autorizaciones apuntándole.
  · El negocio de cada correo sale de **la dirección a la que llegó** (`Delivered-To`, `To`, `Cc`),
    no de con qué permiso se leyó. Un correo dirigido al alias de GutLyn se marca GutLyn aunque se
    lea con el permiso de Zenvrax, que es lo que el operador necesita distinguir.
  · La agenda no se puede repartir: un alias no tiene calendario propio.

QUE NO HACE, y es lo importante:

  · **No guarda ni un correo.** Se leen, se resumen para la pregunta que se esta contestando, y se
    olvidan. Una copia seria un tercer sitio con los datos personales del operador, que es
    exactamente lo que toda esta arquitectura evita.
  · **No responde ni archiva.** Con los permisos de hoy (`gmail.readonly`) no puede, y cuando pueda
    seguira necesitando el OK: enviar un correo sale al mundo igual que publicar un post.

LO QUE SE PIDE A GOOGLE, y por que asi:

  · Del correo, solo la BANDEJA DE ENTRADA sin leer de los ultimos dias. Pedir todo el buzon seria
    lento, caro en contexto y no contesta mejor a "que tengo pendiente".
  · Solo las CABECERAS (de, para, asunto, fecha) y el resumen corto que Google ya da. El cuerpo
    entero de veinte correos no cabe en un contexto sin encarecer cada pregunta, y para triar no
    hace falta.
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from servicio import google

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDARIO = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _cabecera(mensaje: dict, nombre: str) -> str:
    for h in (mensaje.get("payload") or {}).get("headers") or []:
        if h.get("name", "").lower() == nombre.lower():
            return h.get("value", "")
    return ""


def _abre_correo(buzon: str, hilo: str) -> str:
    """El enlace que abre ese hilo en Gmail.

    `?authuser=<correo>` y no `/mail/u/<correo>/`: ese tramo de la ruta espera el NUMERO de la
    cuenta (0, 1, 2), y ponerle un correo hace que Gmail conteste "Temporary Error (404)". Pasó en
    la primera prueba real, el 2026-09-27.
    """
    return ("https://mail.google.com/mail/?authuser=" + urllib.parse.quote(buzon)
            + "#inbox/" + hilo)


def _de_quien_es(destinos: str, negocios: list[str]) -> str:
    """A que negocio pertenece un correo, segun la direccion a la que llego.

    `negocios` viene ordenado: el primero es el dueño del buzon y hace de valor por defecto. Se
    mira el dominio del alias, no la direccion entera, porque `ghidalgo@`, `hola@` y `info@` del
    mismo dominio son el mismo negocio.
    """
    bajo = destinos.lower()
    for negocio in negocios[1:]:
        dominio = google.direcciones().get(negocio, "").rsplit("@", 1)[-1].lower()
        if dominio and "@" + dominio in bajo:
            return negocio
    return negocios[0]


def _filtro_del_negocio(cual: str, negocios: list[str]) -> str:
    """El trozo de consulta que deja SOLO el correo de ese negocio.

    POR QUE NO BASTA CON REPARTIR DESPUES (2026-09-29). El operador pidio separar el correo por
    negocio. Antes se traian los 12 sin leer mas recientes y se repartian por destinatario, y eso
    tiene un fallo que no se ve: medido ese dia, habia 50 sin leer en siete dias y solo UNO era de
    GutLyn. Con doce, ese uno se quedaba fuera casi siempre, y el apartado de GutLyn habria salido
    vacio sin estarlo. Un grupo vacio por el recorte se lee igual que uno vacio de verdad.

    Asi que cada negocio pide los suyos: los 12 mas recientes DE CADA UNO.

    El dueño del buzon se lleva "todo lo que NO es de los alias", y no una lista de sus propios
    dominios: un correo dirigido a una direccion que nadie declaro tiene que aparecer en algun
    sitio, y el sitio natural es el buzon que lo recibio.
    """
    otros = [n for n in negocios[1:] if google.direcciones().get(n)]
    dominios = [google.direcciones()[n].rsplit("@", 1)[-1].lower() for n in otros]
    if cual == negocios[0]:
        return " ".join(f"-to:{d} -cc:{d}" for d in dominios)
    d = google.direcciones().get(cual, "").rsplit("@", 1)[-1].lower()
    return f"{{to:{d} cc:{d} deliveredto:{d}}}" if d else ""


def correos(negocio: str, cuantos: int = 12, dias: int = 7,
            buzon: str = "", negocios: list[str] | None = None,
            solo_de: str = "") -> list[dict]:
    """Los correos sin leer de la bandeja de un buzon. Lanza NoAutorizado si no hay permiso.

    `solo_de` acota a un negocio (el dueño del buzon o uno de sus alias). Sin el, vienen todos.
    """
    negocios = negocios or [negocio]
    buzon = buzon or google.CUENTAS.get(negocio, "")
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y/%m/%d")
    filtro = _filtro_del_negocio(solo_de, negocios) if solo_de else ""
    consulta = urllib.parse.quote(f"in:inbox is:unread after:{desde} {filtro}".strip())
    lista = google.pide(negocio, f"{GMAIL}/messages?maxResults={cuantos}&q={consulta}")
    fuera = []
    for m in lista.get("messages") or []:
        # `metadata` en vez del mensaje entero: trae las cabeceras y el resumen, y nada del cuerpo.
        detalle = google.pide(
            negocio,
            f"{GMAIL}/messages/{m['id']}?format=metadata"
            "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
            "&metadataHeaders=To&metadataHeaders=Cc&metadataHeaders=Delivered-To")
        destinos = " ".join(_cabecera(detalle, c) for c in ("Delivered-To", "To", "Cc"))
        fuera.append({
            # El id viaja para poder responder desde la propia lista.
            "id": m["id"],
            # El negocio sale de A QUIEN iba, no de con que permiso se leyo: con un alias, las dos
            # autorizaciones son el mismo buzon y lo segundo no distingue nada.
            "negocio": _de_quien_es(destinos, negocios),
            "de": _cabecera(detalle, "From"),
            "asunto": _cabecera(detalle, "Subject") or "(sin asunto)",
            "fecha": _cabecera(detalle, "Date"),
            "resumen": (detalle.get("snippet") or "").strip()[:200],
            # El hilo y no el mensaje: es lo que entiende la direccion de Gmail. Zeno enseña, y el
            # trabajo se hace donde ya se hace.
            "abrir": _abre_correo(buzon, m.get("threadId") or m["id"]),
        })
    return fuera


#: Cuanto se mira hacia delante en la agenda. Empezo en 3 dias y la pantalla decia "nada en los
#: proximos dias" teniendo una cita a la vuelta: con una agenda poco cargada, tres dias enseñan
#: vacio casi siempre y el apartado parece roto.
DIAS_DE_AGENDA = 14


def agenda(negocio: str, dias: int = DIAS_DE_AGENDA, buzon: str = "") -> list[dict]:
    """Las citas de los proximos dias de un buzon."""
    buzon = buzon or google.CUENTAS.get(negocio, "")
    ahora = datetime.now(timezone.utc)
    parametros = urllib.parse.urlencode({
        "timeMin": ahora.isoformat().replace("+00:00", "Z"),
        "timeMax": (ahora + timedelta(days=dias)).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 20,
    })
    datos = google.pide(negocio, f"{CALENDARIO}?{parametros}")
    fuera = []
    for e in datos.get("items") or []:
        inicio = (e.get("start") or {})
        enlace = e.get("htmlLink") or ""
        if enlace:
            # Mismo motivo que en el correo: sin decir de quien es la cuenta, el enlace abre en la
            # sesion que el navegador tenga delante, que puede ser otra.
            enlace += ("&" if "?" in enlace else "?") + "authuser=" + urllib.parse.quote(buzon)
        fuera.append({
            "negocio": negocio,
            # El id viaja para poder mover o cancelar desde la propia lista. Sin el habia que
            # abrir Google para cualquier cambio, que es la mitad del trabajo de una agenda.
            "id": e.get("id") or "",
            "titulo": e.get("summary") or "(sin titulo)",
            # Un evento de dia entero trae `date` y no `dateTime`: leer solo dateTime dejaba fuera
            # justo los que ocupan el dia completo.
            "cuando": inicio.get("dateTime") or inicio.get("date") or "",
            "todo_el_dia": "date" in inicio and "dateTime" not in inicio,
            "con": [a.get("email") for a in (e.get("attendees") or []) if a.get("email")][:5],
            "abrir": enlace,
        })
    return fuera


def _por_buzon(conectadas: dict) -> dict[str, list[str]]:
    """Agrupa los negocios conectados por el buzon REAL al que apuntan.

    Es la pieza que evita el duplicado: dos autorizaciones sobre el mismo buzon (porque una es un
    alias de la otra) forman UN grupo y se leen una sola vez.
    """
    grupos: dict[str, list[str]] = {}
    for negocio, d in conectadas.items():
        buzon = (d.get("buzon") or d.get("cuenta") or negocio).lower()
        grupos.setdefault(buzon, []).append(negocio)
    return grupos


def bandeja() -> tuple[dict, list[str]]:
    """El correo y la agenda de los buzones conectados, con sus fallos aparte.

    Un buzon caido NO tumba al otro: se devuelve lo que hay y se dice lo que falta. Un resumen corto
    sin aviso se lee como "tienes poco correo", y con eso se toman decisiones.
    """
    conectadas = google.conectadas()
    fuera: dict = {"correos": [], "agenda": [], "cuentas": conectadas, "buzones": []}
    fallos = []
    vistos: set[str] = set()      # ids ya añadidos: un correo no puede salir dos veces
    for negocio in google.CUENTAS:
        if negocio not in conectadas:
            fallos.append(f"{google.CUENTAS[negocio]}: sin conectar todavia")

    for buzon, negocios in _por_buzon(conectadas).items():
        # El primero manda: es con cuyo permiso se lee y el negocio por defecto de lo que llegue.
        principal = negocios[0]
        # Los alias declarados viajan con el buzon: son los que dan nombre al negocio de cada
        # correo, aunque no tengan autorizacion propia porque no la necesitan.
        #
        # SOLO LOS QUE NO TIENEN BUZON PROPIO (29-sep). Antes se añadian TODOS a TODOS los buzones.
        # Con uno solo daba igual; el dia que GutLyn tenga el suyo, el buzon de Zenvrax seguiria
        # preguntando por correo de GutLyn y lo leeria de donde no es. Lo destapo un test que ya
        # existia, al pasar a preguntar una vez por negocio.
        con_buzon_propio = {n for n, d in conectadas.items() if (d or {}).get("buzon")}
        negocios = negocios + [n for n in google.ALIAS
                               if n not in negocios and n not in con_buzon_propio]
        fuera["buzones"].append({"buzon": buzon, "negocios": negocios,
                                 "alias_de": negocios[1:]})
        # UNA CONSULTA POR NEGOCIO, no una y a repartir. Ver `_filtro_del_negocio`: con una sola,
        # el negocio que recibe poco correo desaparecia detras del recorte.
        #
        # Y SE DEDUPLICA POR ID, que es la contrapartida de preguntar dos veces al MISMO buzon: si
        # un filtro fallara o dos negocios reclamaran el mismo correo (va dirigido a los dos, por
        # ejemplo), saldria repetido en la pantalla. Lo caze al romper los tests que ya vigilaban
        # justo eso desde que existen los alias.
        for cual in negocios:
            try:
                for c in correos(principal, buzon=buzon, negocios=negocios, solo_de=cual):
                    # `get` y no `c["id"]`: un correo sin id no puede tumbar la bandeja entera.
                    # Sin id no se puede deduplicar, asi que pasa: mejor un repetido que perder
                    # el correo o dejar la pantalla en blanco por un KeyError.
                    ident = c.get("id")
                    if ident and ident in vistos:
                        continue
                    if ident:
                        vistos.add(ident)
                    fuera["correos"].append(c)
            except google.NoAutorizado as e:
                fallos.append(f"{buzon} (correos): {e}")
                break                                     # sin permiso no hay nada que reintentar
            except Exception as e:                        # noqa: BLE001
                fallos.append(f"{google.direcciones().get(cual, cual)} (correos): "
                              f"{type(e).__name__}")
        try:
            fuera["agenda"] += agenda(principal, buzon=buzon)
        except google.NoAutorizado as e:
            fallos.append(f"{buzon} (agenda): {e}")
        except Exception as e:                            # noqa: BLE001
            fallos.append(f"{buzon} (agenda): {type(e).__name__}")

    fuera["agenda"].sort(key=lambda c: c["cuando"])
    return fuera, fallos
