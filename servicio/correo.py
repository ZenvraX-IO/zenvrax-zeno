# -*- coding: utf-8 -*-
"""Redactar una respuesta y dejarla como BORRADOR en tu Gmail. Nunca enviarla.

EL ESCALÓN INTERMEDIO, y por eso existe. Enviar un correo sale al mundo igual que publicar un post:
llega a un cliente y no se recoge. Un borrador no sale de tu buzón, se edita donde ya trabajas y se
manda tú cuando quieras. Zeno escribe; la decisión de enviar sigue siendo tuya, y sigue estando en
Gmail, que es donde ya está.

EL BORRADOR VIVE EN TU GMAIL, no en Zeno. Así se lee desde el móvil, desde el portátil o desde donde
sea, y si Zeno desapareciera mañana los borradores seguirían ahí. Es la misma decisión que con los
correos: Zeno no es el sitio donde vive el contenido.

AQUÍ SÍ SE LEE EL CUERPO DEL CORREO, y es una excepción deliberada a lo que hace el resto del
módulo. La bandeja se lee solo con cabeceras y el resumen corto, porque el cuerpo de veinte correos
no cabe en un contexto sin encarecer cada pregunta. Pero para contestar UNO hace falta leerlo
entero: una respuesta escrita desde el asunto y las dos primeras líneas se nota, y se nota mal. Se
lee ese mensaje, se usa, y no se guarda.
"""
from __future__ import annotations

import base64
import secrets
import time
import urllib.parse
from email.message import EmailMessage

from servicio import google, personal

GMAIL = personal.GMAIL

_VALES: dict[str, dict] = {}
_VIVE = 900.0                # quince minutos: un borrador no sale al mundo, no hay prisa


class NoSePuede(RuntimeError):
    """No se puede preparar o guardar el borrador, y el mensaje dice por que."""


def _texto_de(parte: dict) -> str:
    """El texto plano de un mensaje de Gmail, bajando por las partes si hace falta."""
    if parte.get("mimeType") == "text/plain":
        datos = (parte.get("body") or {}).get("data") or ""
        if datos:
            return base64.urlsafe_b64decode(datos + "=" * (-len(datos) % 4)).decode(
                "utf-8", "replace")
    for hija in parte.get("parts") or []:
        t = _texto_de(hija)
        if t:
            return t
    return ""


def lee_entero(negocio: str, ident: str, tope: int = 4000) -> dict:
    """Un correo con su cuerpo. Solo se llama al preparar una respuesta a ESE correo."""
    m = google.pide(negocio, f"{GMAIL}/messages/{urllib.parse.quote(ident)}?format=full")
    cabecera = personal._cabecera
    return {
        "id": m.get("id"), "hilo": m.get("threadId"),
        "de": cabecera(m, "From"), "para": cabecera(m, "To"),
        "asunto": cabecera(m, "Subject") or "(sin asunto)",
        "mensaje_id": cabecera(m, "Message-ID"),
        "referencias": cabecera(m, "References"),
        # Recortado: un hilo largo con diez respuestas citadas abajo no aporta nada para contestar
        # y multiplica lo que cuesta cada redaccion.
        "cuerpo": (_texto_de(m.get("payload") or {}) or m.get("snippet") or "").strip()[:tope],
    }


#: Direcciones que no leen a nadie. Se avisa, no se bloquea: alguna sale de un buzon que si
#: atiende gente, y decidir por el operador que un correo no merece respuesta seria pasarse.
_NADIE_LEE = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
              "mailer-daemon", "postmaster", "notifications@", "notification@",
              "facebookmail.com", "bounce", "@e.linkedin.com")


def contesta_alguien(direccion: str) -> bool:
    """Si esa direccion parece leida por una persona.

    Salio de la primera prueba real: el correo sin leer mas reciente era un aviso de Facebook, y
    Zeno preparo tan campante una respuesta a `pageupdates@facebookmail.com`. El borrador estaba
    perfecto y no servia para nada.
    """
    d = (direccion or "").lower()
    return not any(x in d for x in _NADIE_LEE)


def _direccion(de: str) -> str:
    """La direccion sola de un "Nombre <correo@sitio>"."""
    if "<" in de and ">" in de:
        return de[de.index("<") + 1:de.index(">")].strip()
    return de.strip()


def prepara(negocio: str, ident: str, texto: str) -> dict:
    """Guarda un borrador listo y devuelve un vale. NO toca Gmail todavia."""
    if not (texto or "").strip():
        raise NoSePuede("el borrador esta vacio")
    try:
        original = lee_entero(negocio, ident)
    except google.NoAutorizado:
        raise
    except Exception as e:                                # noqa: BLE001
        raise NoSePuede(f"no encuentro ese correo ({type(e).__name__})") from e

    para = _direccion(original["de"])
    if not para:
        raise NoSePuede("ese correo no dice de quien viene, no se a quien responder")
    asunto = original["asunto"]
    if not asunto.lower().startswith("re:"):
        asunto = "Re: " + asunto

    vale = secrets.token_urlsafe(18)
    ahora = time.time()
    for v, d in list(_VALES.items()):
        if ahora - d["nacida"] > _VIVE:
            _VALES.pop(v, None)
    _VALES[vale] = {"nacida": ahora, "negocio": negocio, "para": para, "asunto": asunto,
                    "texto": texto.strip(), "hilo": original["hilo"],
                    "mensaje_id": original["mensaje_id"],
                    "referencias": original["referencias"]}
    return {"vale": vale, "para": para, "asunto": asunto, "texto": texto.strip(),
            # Se dice con todas las letras, porque es justo lo que lo distingue de enviar.
            "solo_borrador": True,
            "que_pasa": "Se guarda en tu Gmail como borrador. No se envia.",
            "nadie_lo_lee": not contesta_alguien(para)}


def guarda(vale: str) -> dict:
    """LO UNICO que escribe en Gmail. Crea el borrador; no envia nada."""
    d = _VALES.pop(vale, None)
    if not d or time.time() - d["nacida"] > _VIVE:
        raise NoSePuede("ese borrador ha caducado: vuelve a prepararlo")

    m = EmailMessage()
    m["To"] = d["para"]
    m["Subject"] = d["asunto"]
    # Sin estas dos cabeceras el borrador sale como un correo suelto y rompe el hilo: el que lo
    # recibe ve una conversacion nueva y pierde el contexto de lo que estaba contestando.
    if d["mensaje_id"]:
        m["In-Reply-To"] = d["mensaje_id"]
        m["References"] = (d["referencias"] + " " + d["mensaje_id"]).strip()
    m.set_content(d["texto"])

    cuerpo = {"message": {
        "raw": base64.urlsafe_b64encode(m.as_bytes()).decode(),
        # `threadId` es lo que hace que el borrador aparezca DENTRO de la conversacion en Gmail,
        # en vez de suelto en la carpeta de borradores sin contexto.
        "threadId": d["hilo"],
    }}
    hecho = google.escribe(d["negocio"], f"{GMAIL}/drafts", cuerpo)
    ident = hecho.get("id", "")
    return {
        "guardado": True, "para": d["para"], "asunto": d["asunto"], "id": ident,
        "enviado": False,
        # El enlace abre el borrador en Gmail, que es donde se revisa y desde donde se manda.
        "abrir": ("https://mail.google.com/mail/?authuser="
                  + urllib.parse.quote(google.CUENTAS.get(d["negocio"], ""))
                  + "#drafts" + (("/" + ident) if ident else "")),
    }
