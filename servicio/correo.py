# -*- coding: utf-8 -*-
"""Redactar una respuesta, dejarla como borrador o enviarla.

EL ESCALÓN INTERMEDIO SIGUE SIENDO EL DEFECTO. Enviar un correo sale al mundo igual que publicar un
post: llega a un cliente y no se recoge. Así que el botón grande sigue siendo el borrador, que no
sale de tu buzón y se edita donde ya trabajas.

ENVIAR SE AÑADIÓ EL 2026-09-28, porque era el único trabajo diario que empezaba en Zeno y terminaba
fuera: Zeno escribía la respuesta y había que abrir Gmail solo para pulsar enviar. Pide el PIN, como
todo lo que no se deshace, y NO se puede hacer hablando.

Y AQUÍ HAY UN HALLAZGO QUE CONVIENE NO OLVIDAR. Este módulo decía "nunca enviarla" y el comentario
de `google.PERMISO_BORRADOR` decía "No envia nada". Era falso desde el 27-sep: `gmail.compose`, el
permiso que el operador ya tenía concedido, dice literalmente *"Manage drafts and send emails"*. O
sea que la barrera que creíamos tener no existía: lo único que impedía enviar era que no había
código que lo hiciera. Una barrera imaginaria es peor que ninguna, porque se confía en ella.

SE ENVÍA POR EL CAMINO DEL BORRADOR (crear y luego `drafts/{id}/send`), no con `messages/send`
directo, por dos razones: es el camino que `gmail.compose` garantiza sin pedir un permiso nuevo, y
si el envío falla el texto queda guardado en Gmail en vez de perderse.

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
#: Cinco minutos desde que se anadio el envio. Antes eran quince "porque un borrador no sale al
#: mundo": ahora el mismo vale puede mandar un correo, asi que vale lo que vale una confirmacion
#: de algo irreversible y no lo que vale guardar un texto.
_VIVE = 300.0


class NoSePuede(RuntimeError):
    """No se puede preparar o guardar el borrador, y el mensaje dice por que."""


class NoSeSabe(RuntimeError):
    """Se mando la peticion de envio y no se supo el resultado.

    ES DISTINTO de NoSePuede y por eso es otra clase: "no se ha podido" invita a reintentar, y
    reintentar un envio que si salio manda el correo dos veces al mismo cliente.
    """


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
            # EL VALE SIRVE PARA LOS DOS CAMINOS, y por eso aqui ya no se promete que no se envia:
            # hasta el 28-sep esta respuesta decia "No se envia" y era cierto porque no habia otro
            # camino. Ahora lo decide el boton que se pulse, asi que se dicen las dos opciones y
            # cual sale al mundo.
            "solo_borrador": False,
            "que_pasa": "Puedes guardarlo como borrador en tu Gmail, o enviarlo.",
            "enviar_sale_al_mundo": True,
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


def envia(vale: str) -> dict:
    """Manda la respuesta. IRREVERSIBLE: llega a quien sea y no se recoge.

    Dos pasos a proposito. Primero se crea el borrador y solo despues se manda: si el envio falla,
    el texto queda guardado en Gmail y el trabajo no se pierde. Con `messages/send` directo, un
    fallo se lleva por delante lo escrito.

    QUIEN COMPRUEBA EL PIN NO ES ESTO, es el endpoint, igual que en el ejecutor. Aqui no hay sesion.
    """
    d = _VALES.get(vale)
    if not d or time.time() - d["nacida"] > _VIVE:
        _VALES.pop(vale, None)
        raise NoSePuede("esa respuesta ha caducado: vuelve a prepararla")

    # El borrador primero, con el vale TODAVIA vivo: si esto falla, no se ha quemado nada y se
    # puede reintentar sin volver a escribir el texto.
    guardado = guarda(vale)                      # esto ya consume el vale
    ident = guardado.get("id", "")
    if not ident:
        # Sin id no hay nada que mandar, y el texto esta a salvo en Gmail. Se dice tal cual.
        raise NoSePuede("el borrador se ha guardado pero Gmail no ha devuelto su id: "
                        "esta en tu Gmail, mandalo desde ahi")

    try:
        google.escribe(d["negocio"], f"{GMAIL}/drafts/send", {"id": ident})
    except Exception as e:                                # noqa: BLE001
        # AQUI NO SE SABE SI SALIO. Un timeout despues de mandar la peticion puede significar que
        # el correo ya se fue. Decir "no se ha enviado" seria mentir con seguridad y llevaria a
        # reintentar, o sea a mandarlo dos veces al mismo cliente.
        raise NoSeSabe(
            f"no he podido saber si ha salido ({type(e).__name__}). El borrador esta en tu Gmail: "
            "mira en Enviados antes de repetirlo") from e

    return {"enviado": True, "para": d["para"], "asunto": d["asunto"], "id": ident,
            "guardado": True,
            # A Enviados, no a borradores: es donde el operador va a comprobarlo.
            "abrir": ("https://mail.google.com/mail/?authuser="
                      + urllib.parse.quote(google.CUENTAS.get(d["negocio"], ""))
                      + "#sent")}
