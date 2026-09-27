# -*- coding: utf-8 -*-
"""La agenda que propone. Zeno busca el hueco, tú confirmas, y solo entonces se crea.

LA REGLA DE ESTA PIEZA, decidida por el operador el 2026-09-27 sobre tres opciones: *"que proponga,
tú confirmas"*. No es una preferencia de estilo, es lo que separa esta pieza del resto de Zeno:
hasta aquí todo era leer, y una cita creada SALE AL MUNDO. Si lleva invitados, les llega un correo
que ya no se puede recoger; y aunque no los lleve, ocupa un hueco que luego alguien da por bueno.

Por eso el flujo tiene dos tiempos y no uno:

  1. `propone(...)` calcula, guarda la propuesta con un vale y NO toca Google.
  2. `confirma(vale)` es lo único que escribe, y solo funciona con un vale que exista.

Un vale caduca a los diez minutos. Si caduca, se vuelve a proponer: es barato. Lo caro es lo otro,
que una pantalla vieja abierta en el móvil cree una cita al pulsar sin que nadie la haya mirado.

LO QUE MIRA PARA PROPONER, y por qué así:

  · **El horario de trabajo**, no las 24 horas. Un hueco a las tres de la mañana es un hueco y no
    sirve de nada. Configurable, porque no es una verdad universal.
  · **Los eventos de día completo NO bloquean.** Un festivo o un "viaje a Madrid" ocupan el día
    entero en el calendario pero no impiden una llamada. Tratarlos como ocupado dejaba la semana
    sin un solo hueco.
  · **Los que has rechazado tampoco.** Si dijiste que no a una reunión, su hora está libre.
"""
from __future__ import annotations

import os
import re
import secrets
import time
import urllib.parse
from datetime import datetime, time as hora_del_dia, timedelta
from zoneinfo import ZoneInfo

from servicio import google

CALENDARIO = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

ZONA = ZoneInfo(os.environ.get("ZENO_ZONA", "Europe/Madrid"))
#: El horario en el que tiene sentido proponer algo. Fuera de esto hay hueco, pero no sirve.
ABRE = int(os.environ.get("ZENO_AGENDA_ABRE", "9"))
CIERRA = int(os.environ.get("ZENO_AGENDA_CIERRA", "19"))
#: Días de la semana que cuentan (0 = lunes). Sábado y domingo fuera salvo que se diga.
LABORABLES = {int(d) for d in os.environ.get("ZENO_AGENDA_DIAS", "0,1,2,3,4").split(",") if d != ""}
#: Aire antes y después de cada cita: dos reuniones pegadas no son dos huecos reales.
COLCHON = timedelta(minutes=int(os.environ.get("ZENO_AGENDA_COLCHON", "15")))

DURACION_POR_DEFECTO = 30

#: Las propuestas vivas. En memoria a propósito: una propuesta perdida se vuelve a pedir en un
#: segundo, y guardarlas seria estado nuevo que hay que limpiar y que sobrevive a lo que no debe.
_PROPUESTAS: dict[str, dict] = {}
_VIVE = 600.0


class NoSePuede(RuntimeError):
    """La propuesta no vale, ha caducado, o falta el permiso para escribir en el calendario."""


def _ahora() -> datetime:
    return datetime.now(ZONA)


def _lee(txt: str) -> datetime | None:
    """Una fecha de Google a hora local. Devuelve None si es de día completo (trae solo la fecha)."""
    if not txt or len(txt) <= 10:
        return None
    return datetime.fromisoformat(txt.replace("Z", "+00:00")).astimezone(ZONA)


def ocupado(negocio: str, desde: datetime, hasta: datetime) -> list[tuple[datetime, datetime]]:
    """Los tramos realmente ocupados, ya ordenados y con el colchón puesto."""
    q = urllib.parse.urlencode({
        "timeMin": desde.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "timeMax": hasta.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
    })
    datos = google.pide(negocio, f"{CALENDARIO}?{q}")
    tramos = []
    for e in datos.get("items") or []:
        if e.get("status") == "cancelled":
            continue
        # Si el operador rechazó la invitación, esa hora está libre. Contarla como ocupada deja la
        # semana sin huecos por reuniones a las que ni siquiera va.
        if any(a.get("self") and a.get("responseStatus") == "declined"
               for a in (e.get("attendees") or [])):
            continue
        a = _lee((e.get("start") or {}).get("dateTime", ""))
        b = _lee((e.get("end") or {}).get("dateTime", ""))
        # Día completo: bloquea el día en la vista pero no impide una llamada. Un festivo no es una
        # reunión, y tratarlo como ocupado dejaba semanas enteras sin un hueco.
        if not a or not b:
            continue
        tramos.append((a - COLCHON, b + COLCHON))
    return sorted(tramos)


#: Cada cuanto se ofrece un hueco dentro de un rato libre. Sin esto, una mañana entera libre daba
#: UN solo hueco, el de primera hora, y proponer una cita a las 9:00 o nada no es proponer.
PASO = timedelta(minutes=int(os.environ.get("ZENO_AGENDA_PASO", "30")))


def _libres_del_dia(dia, tramos, ahora, dura):
    """Los ratos libres de un dia laborable, ya recortados al horario y a lo que queda de hoy."""
    if dia.weekday() not in LABORABLES:
        return []
    abre = datetime.combine(dia, hora_del_dia(ABRE), ZONA)
    cierra = datetime.combine(dia, hora_del_dia(CIERRA), ZONA)
    punto, ratos = max(abre, ahora), []
    for a, b in tramos:
        if b <= punto or a >= cierra:
            continue
        if a - punto >= dura:
            ratos.append((punto, min(a, cierra)))
        punto = max(punto, b)
    if cierra - punto >= dura:
        ratos.append((punto, cierra))
    return ratos


def _redondea(cuando):
    """A la media hora siguiente. Nadie queda a las 09:07, y un hueco asi no se lee como una opcion."""
    sobra = (cuando.minute % 30) * 60 + cuando.second
    return (cuando + timedelta(seconds=(1800 - sobra) if sobra else 0)).replace(
        second=0, microsecond=0)


def huecos(negocio: str, minutos: int = DURACION_POR_DEFECTO, dias: int = 7,
           cuantos: int = 8) -> list[dict]:
    """Los primeros huecos de trabajo donde cabe algo de esa duracion.

    Se ofrecen VARIOS por rato libre, cada media hora. Antes salia uno por dia: una mañana entera
    libre daba un unico hueco a primera hora, o sea "a las nueve o nada", que no es una propuesta.
    """
    dura = timedelta(minutes=minutos)
    ahora = _ahora()
    fin = ahora + timedelta(days=dias)
    tramos = ocupado(negocio, ahora, fin)

    libres = []
    dia = ahora.date()
    while dia <= fin.date() and len(libres) < cuantos:
        for desde, hasta in _libres_del_dia(dia, tramos, ahora, dura):
            punto = _redondea(desde)
            while punto + dura <= hasta and len(libres) < cuantos:
                libres.append(punto)
                punto += PASO
            if len(libres) >= cuantos:
                break
        dia += timedelta(days=1)

    return [{"desde": h.isoformat(), "hasta": (h + dura).isoformat(),
             "etiqueta": _en_palabras(h, minutos)} for h in libres[:cuantos]]


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _en_palabras(cuando: datetime, minutos: int) -> str:
    """Como lo diria una persona: "mañana jueves a las 10:00, 30 min"."""
    hoy = _ahora().date()
    delta = (cuando.date() - hoy).days
    if delta == 0:
        dia = "hoy"
    elif delta == 1:
        dia = "mañana " + _DIAS[cuando.weekday()]
    elif delta < 7:
        dia = "el " + _DIAS[cuando.weekday()]
    else:
        dia = f"el {cuando.day} de {_MESES[cuando.month - 1]}"
    return f"{dia} a las {cuando:%H:%M}, {minutos} min"


def choques(negocio: str, dias: int = 14) -> list[dict]:
    """Las citas que se pisan. Es lo que una agenda leida de un vistazo no enseña."""
    ahora = _ahora()
    q = urllib.parse.urlencode({
        "timeMin": ahora.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "timeMax": (ahora + timedelta(days=dias)).astimezone(
            ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
    })
    eventos = []
    for e in (google.pide(negocio, f"{CALENDARIO}?{q}").get("items") or []):
        a = _lee((e.get("start") or {}).get("dateTime", ""))
        b = _lee((e.get("end") or {}).get("dateTime", ""))
        if a and b and e.get("status") != "cancelled":
            eventos.append((a, b, e.get("summary") or "(sin titulo)", e.get("htmlLink") or ""))
    eventos.sort()
    fuera = []
    for i in range(len(eventos) - 1):
        a1, b1, t1, l1 = eventos[i]
        a2, b2, t2, l2 = eventos[i + 1]
        # Se comparan las horas de verdad, sin colchon: dos reuniones seguidas no son un choque,
        # y avisar de ellas convertiria el aviso en ruido que se deja de mirar.
        if a2 < b1:
            fuera.append({"uno": t1, "otro": t2, "cuando": _en_palabras(a2, 0).split(",")[0],
                          "desde": a2.isoformat(), "abrir": l2 or l1})
    return fuera


# ---------------------------------------------------------------- proponer, y solo despues crear

def propone(negocio: str, titulo: str, desde: str, minutos: int = DURACION_POR_DEFECTO,
            con: list[str] | None = None, donde: str = "") -> dict:
    """Prepara una cita y devuelve un vale. NO toca Google: aqui todavia no existe nada."""
    if not titulo.strip():
        raise NoSePuede("la cita necesita un titulo")
    try:
        cuando = datetime.fromisoformat(desde)
    except ValueError:
        raise NoSePuede(f"no entiendo la fecha {desde!r}") from None
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=ZONA)
    if cuando < _ahora():
        raise NoSePuede("esa hora ya ha pasado")

    invitados = _revisa_invitados(con or [])
    vale = secrets.token_urlsafe(18)
    ahora = time.time()
    for v, d in list(_PROPUESTAS.items()):
        if ahora - d["nacida"] > _VIVE:
            _PROPUESTAS.pop(v, None)
    _PROPUESTAS[vale] = {
        "nacida": ahora, "negocio": negocio, "titulo": titulo.strip(),
        "desde": cuando, "hasta": cuando + timedelta(minutes=minutos),
        "con": invitados, "donde": donde.strip(),
    }
    return {
        "vale": vale, "titulo": titulo.strip(), "cuando": _en_palabras(cuando, minutos),
        "desde": cuando.isoformat(), "minutos": minutos, "con": invitados, "donde": donde.strip(),
        # Se dice EN LA PROPUESTA si va a salir al mundo, antes de confirmar y no despues.
        "avisa_a_invitados": bool(invitados),
        "choca_con": [c["uno"] for c in _choca_aqui(negocio, cuando, minutos)],
    }


#: Una direccion de correo, comprobada sin pretensiones: hay arroba, hay algo a cada lado y hay un
#: punto en el dominio. No valida que exista, valida que no sea una errata evidente.
_CORREO = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")


def _revisa_invitados(con: list[str]) -> list[str]:
    """Los invitados, limpios, o NoSePuede con el que esta mal escrito.

    Se revisa porque invitar sale al mundo: Google manda un correo a cada direccion de la lista. Una
    errata no da error, crea la cita y manda la invitacion a otro sitio. Y esto importa mas cuando
    la cita se dicte por voz, donde una direccion mal entendida es lo normal, no la excepcion: mejor
    que Zeno diga "no te he entendido el correo" a que invite a un desconocido.
    """
    fuera = []
    for c in con:
        c = c.strip().strip("<>").rstrip(".,;")
        if not c:
            continue
        if not _CORREO.match(c):
            raise NoSePuede(f"esto no parece un correo: {c}")
        if c.lower() not in [x.lower() for x in fuera]:
            fuera.append(c)
    return fuera


def _choca_aqui(negocio: str, cuando: datetime, minutos: int) -> list[dict]:
    """Si ya hay algo en ese rato. Se comprueba al PROPONER, que es cuando se puede cambiar."""
    fin = cuando + timedelta(minutes=minutos)
    try:
        tramos = ocupado(negocio, cuando - timedelta(hours=2), fin + timedelta(hours=2))
    except Exception:                                    # noqa: BLE001
        return []
    return [{"uno": "algo ya puesto"} for a, b in tramos
            if a + COLCHON < fin and b - COLCHON > cuando]


def confirma(vale: str) -> dict:
    """LO UNICO que escribe en Google. Sin un vale vivo no hace nada."""
    d = _PROPUESTAS.pop(vale, None)
    # `que` marca las propuestas de mover y cancelar, que comparten este mismo almacen. Sin esta
    # comprobacion, un vale de cancelar metido aqui crearia una cita a medias en vez de fallar, y
    # el operador veria "creada" sin que se hubiera cancelado nada.
    if not d or time.time() - d["nacida"] > _VIVE or "que" in d:
        raise NoSePuede("esa propuesta ha caducado: vuelve a pedirla")
    cuerpo = {
        "summary": d["titulo"],
        "start": {"dateTime": d["desde"].isoformat()},
        "end": {"dateTime": d["hasta"].isoformat()},
    }
    if d["donde"]:
        cuerpo["location"] = d["donde"]
    if d["con"]:
        cuerpo["attendees"] = [{"email": c} for c in d["con"]]
    # `sendUpdates` solo cuando hay invitados: es el parametro que decide si SALE un correo. Con
    # "all" por defecto, una cita para uno mismo no manda nada, pero dejarlo escrito asi hace que la
    # linea diga lo que hace.
    q = "?sendUpdates=" + ("all" if d["con"] else "none")
    creada = google.escribe(d["negocio"], CALENDARIO + q, cuerpo)
    return {"creada": True, "titulo": d["titulo"], "cuando": _en_palabras(d["desde"], 0),
            "abrir": creada.get("htmlLink", ""), "id": creada.get("id", ""),
            "avisados": d["con"]}


# ---------------------------------------------------------------- mover y cancelar

def _mira(negocio: str, ident: str) -> dict:
    """La cita tal cual esta en Google. Se lee ANTES de proponer nada."""
    try:
        return google.pide(negocio, f"{CALENDARIO}/{urllib.parse.quote(ident)}")
    except Exception as e:                                # noqa: BLE001
        raise NoSePuede(f"no encuentro esa cita ({type(e).__name__})") from e


def _quien_va(evento: dict) -> list[str]:
    """Los invitados que NO son uno mismo. Son los que reciben el correo si algo cambia."""
    return [a.get("email") for a in (evento.get("attendees") or [])
            if a.get("email") and not a.get("self")]


def propone_cambio(negocio: str, ident: str, nuevo_desde: str,
                   minutos: int | None = None) -> dict:
    """Preparar mover una cita. NO la mueve."""
    e = _mira(negocio, ident)
    try:
        cuando = datetime.fromisoformat(nuevo_desde)
    except ValueError:
        raise NoSePuede(f"no entiendo la fecha {nuevo_desde!r}") from None
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=ZONA)
    if cuando < _ahora():
        raise NoSePuede("esa hora ya ha pasado")

    a = _lee((e.get("start") or {}).get("dateTime", ""))
    b = _lee((e.get("end") or {}).get("dateTime", ""))
    if not a or not b:
        # Un evento de dia entero no tiene hora que mover, y tratarlo como si la tuviera lo
        # convertiria en una cita de media hora sin que nadie lo pidiera.
        raise NoSePuede("esa cita ocupa el dia entero: muevela desde Google")
    dura = minutos if minutos else int((b - a).total_seconds() // 60)
    invitados = _quien_va(e)

    vale = secrets.token_urlsafe(18)
    _PROPUESTAS[vale] = {"nacida": time.time(), "que": "mover", "negocio": negocio, "id": ident,
                         "titulo": e.get("summary") or "(sin titulo)", "desde": cuando,
                         "hasta": cuando + timedelta(minutes=dura), "con": invitados}
    return {"vale": vale, "que": "mover", "titulo": e.get("summary") or "(sin titulo)",
            "antes": _en_palabras(a, int((b - a).total_seconds() // 60)),
            "cuando": _en_palabras(cuando, dura), "con": invitados,
            # Mover una cita con invitados les manda un correo. Es lo que no se deshace.
            "avisa_a_invitados": bool(invitados)}


def propone_baja(negocio: str, ident: str) -> dict:
    """Preparar cancelar una cita. NO la cancela."""
    e = _mira(negocio, ident)
    a = _lee((e.get("start") or {}).get("dateTime", ""))
    invitados = _quien_va(e)
    vale = secrets.token_urlsafe(18)
    _PROPUESTAS[vale] = {"nacida": time.time(), "que": "cancelar", "negocio": negocio,
                         "id": ident, "titulo": e.get("summary") or "(sin titulo)",
                         "con": invitados}
    return {"vale": vale, "que": "cancelar", "titulo": e.get("summary") or "(sin titulo)",
            "cuando": _en_palabras(a, 0) if a else "todo el dia",
            "con": invitados, "avisa_a_invitados": bool(invitados),
            # Cancelar no se deshace desde Zeno: no hay papelera en el calendario.
            "sin_vuelta": True}


def confirma_cambio(vale: str, pin_abierto: bool = True) -> dict:
    """Mueve o cancela de verdad. Con invitados hace falta el PIN, por el mismo motivo que publicar:
    les llega un correo que no se puede recoger."""
    d = _PROPUESTAS.pop(vale, None)
    if not d or time.time() - d["nacida"] > _VIVE or "que" not in d:
        raise NoSePuede("esa propuesta ha caducado: vuelve a pedirla")
    if d["con"] and not pin_abierto:
        _PROPUESTAS[vale] = d              # se devuelve: que falte el PIN no tira la propuesta
        raise NoSePuede("esa cita tiene invitados y les va a llegar un correo: hace falta el PIN")

    avisa = "all" if d["con"] else "none"
    url = f"{CALENDARIO}/{urllib.parse.quote(d['id'])}?sendUpdates={avisa}"
    if d["que"] == "cancelar":
        google.escribe(d["negocio"], url, None, metodo="DELETE")
        return {"hecho": True, "que": "cancelar", "titulo": d["titulo"], "avisados": d["con"]}
    google.escribe(d["negocio"], url, {"start": {"dateTime": d["desde"].isoformat()},
                                       "end": {"dateTime": d["hasta"].isoformat()}},
                   metodo="PATCH")
    return {"hecho": True, "que": "mover", "titulo": d["titulo"],
            "cuando": _en_palabras(d["desde"], 0), "avisados": d["con"]}
