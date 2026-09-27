# -*- coding: utf-8 -*-
"""El correo y la agenda del operador. SOLO LECTURA, y sin guardar nada.

QUE NO HACE, y es lo importante:

  · **No guarda ni un correo.** Se leen, se resumen para la pregunta que se esta contestando, y se
    olvidan. Una copia seria un tercer sitio con los datos personales del operador, que es
    exactamente lo que toda esta arquitectura evita.
  · **No responde ni archiva.** Con los permisos de hoy (`gmail.readonly`) no puede, y cuando pueda
    seguira necesitando el OK: enviar un correo sale al mundo igual que publicar un post.
  · **No mezcla las dos cuentas.** Cada una llega con su negocio puesto y se muestra etiquetada.

LO QUE SE PIDE A GOOGLE, y por que asi:

  · Del correo, solo la BANDEJA DE ENTRADA sin leer de los ultimos dias. Pedir todo el buzon seria
    lento, caro en contexto y no contesta mejor a "que tengo pendiente".
  · Solo las CABECERAS (de, asunto, fecha) y el resumen corto que Google ya da. El cuerpo entero
    de veinte correos no cabe en un contexto sin encarecer cada pregunta, y para triar no hace
    falta.
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


def correos(negocio: str, cuantos: int = 12, dias: int = 7) -> list[dict]:
    """Los correos sin leer de la bandeja de una cuenta. Lanza NoAutorizado si no hay permiso."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y/%m/%d")
    consulta = urllib.parse.quote(f"in:inbox is:unread after:{desde}")
    lista = google.pide(negocio, f"{GMAIL}/messages?maxResults={cuantos}&q={consulta}")
    fuera = []
    for m in lista.get("messages") or []:
        # `metadata` en vez del mensaje entero: trae las cabeceras y el resumen, y nada del cuerpo.
        detalle = google.pide(
            negocio,
            f"{GMAIL}/messages/{m['id']}?format=metadata"
            "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date")
        fuera.append({
            "negocio": negocio,
            "de": _cabecera(detalle, "From"),
            "asunto": _cabecera(detalle, "Subject") or "(sin asunto)",
            "fecha": _cabecera(detalle, "Date"),
            "resumen": (detalle.get("snippet") or "").strip()[:200],
            # El enlace abre el correo en Gmail: Zeno enseña, y el trabajo se hace donde ya se hace.
            "abrir": f"https://mail.google.com/mail/u/{google.CUENTAS.get(negocio, '')}/#inbox/{m['id']}",
        })
    return fuera


def agenda(negocio: str, dias: int = 3) -> list[dict]:
    """Las citas de los proximos dias de una cuenta."""
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
        fuera.append({
            "negocio": negocio,
            "titulo": e.get("summary") or "(sin titulo)",
            # Un evento de dia entero trae `date` y no `dateTime`: leer solo dateTime dejaba fuera
            # justo los que ocupan el dia completo.
            "cuando": inicio.get("dateTime") or inicio.get("date") or "",
            "todo_el_dia": "date" in inicio and "dateTime" not in inicio,
            "con": [a.get("email") for a in (e.get("attendees") or []) if a.get("email")][:5],
            "abrir": e.get("htmlLink") or "",
        })
    return fuera


def bandeja() -> tuple[dict, list[str]]:
    """El correo y la agenda de las DOS cuentas, cada uno con su negocio y sus fallos aparte.

    Una cuenta sin permiso o caida NO tumba la otra: se devuelve lo que hay y se dice lo que falta.
    Un resumen corto sin aviso se lee como "tienes poco correo", y con eso se toman decisiones.
    """
    fuera = {"correos": [], "agenda": [], "cuentas": google.conectadas()}
    fallos = []
    for negocio in google.CUENTAS:
        if negocio not in fuera["cuentas"]:
            fallos.append(f"{google.CUENTAS[negocio]}: sin conectar todavia")
            continue
        for etiqueta, funcion in (("correos", correos), ("agenda", agenda)):
            try:
                fuera[etiqueta] += funcion(negocio)
            except google.NoAutorizado as e:
                fallos.append(f"{google.CUENTAS[negocio]} ({etiqueta}): {e}")
            except Exception as e:                        # noqa: BLE001
                fallos.append(f"{google.CUENTAS[negocio]} ({etiqueta}): {type(e).__name__}")
    fuera["agenda"].sort(key=lambda c: c["cuando"])
    return fuera, fallos
