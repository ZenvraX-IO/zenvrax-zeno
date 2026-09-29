# -*- coding: utf-8 -*-
"""Abrir el cockpit o Xrise desde Zeno sin volver a escribir la contrasena.

EL CASO (2026-09-29). El operador: *"una vez que le doy a abrir desde su plataforma... me envia a
internet y de ahi tengo que volver a validar la contrasena y todo, y no tiene mucho sentido"*.

POR QUE PASABA, medido ese dia. En el iPhone cada aplicacion instalada en la pantalla de inicio
tiene su PROPIO almacen, separado de Safari. El cockpit guarda su sesion ahi dentro; Zeno abre el
enlace en Safari o en el visor interno, que es otro almacen, y alli no hay sesion. Aunque en la
aplicacion del cockpit siga dentro sin tocar nada.

Y SALTAR DE UNA APLICACION INSTALADA A OTRA NO SE PUEDE EN iOS. En Android hay app links; aqui no
existe equivalente para este tipo de aplicaciones. Asi que no se pelea con el sistema: se pide al
sistema de destino un enlace de UN SOLO USO que deja la sesion puesta al abrirse.

LO QUE ESTO NO ES. Zeno no guarda ninguna sesion del cockpit ni de Xrise, ni la puede fabricar: le
PIDE el enlace a cada sistema con la clave que ya tenia, y es cada sistema quien decide si lo da y
a quien deja entrar. Zeno sigue sin tener llave propia de las otras casas.

SI ALGO FALLA, SE ABRE EL ENLACE DE SIEMPRE. Un sistema que no responde, una clave retirada o una
version vieja sin este endpoint no pueden dejar al operador sin poder abrir lo que estaba mirando:
se cae al enlace normal, que pedira la contrasena como hasta hoy. Degradar, no romper.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

#: A donde se le pide el enlace a cada sistema, por dentro de la red de Docker.
DENTRO = {
    "cockpit": os.environ.get("ZENO_COCKPIT_URL", "http://cockpit-api:8802"),
    "xrise": os.environ.get("ZENO_XRISE_URL", "http://ecomops-api:8803"),
}
#: Y como se ven desde fuera, que es lo que trae el enlace del navegador.
FUERA = {
    "cockpit": os.environ.get("ZENO_COCKPIT_WEB", "https://cockpit.zenvrax.com"),
    "xrise": os.environ.get("ZENO_XRISE_WEB", "https://xrise.zenvrax.com"),
}
CLAVE = os.environ.get("ZENO_WRITE_KEY", "")


def de_quien_es(url: str) -> str:
    """De que sistema es esa direccion, o cadena vacia si no es de ninguno.

    Se compara el HOST, no el principio del texto. Con `startswith` bastaria una direccion como
    `https://cockpit.zenvrax.com.otrositio.com/` para que Zeno le pidiera un enlace de entrada al
    cockpit y se lo entregara a quien no es.
    """
    try:
        host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""
    if not host:
        return ""
    for sistema, base in FUERA.items():
        if host == (urllib.parse.urlsplit(base).hostname or "").lower():
            return sistema
    return ""


def _ruta(url: str) -> str:
    """La parte de la direccion que va despues del dominio, para volver a ella tras entrar."""
    p = urllib.parse.urlsplit(url)
    return (p.path or "/") + (("?" + p.query) if p.query else "") + (("#" + p.fragment) if p.fragment else "")


def enlace_que_entra(url: str, tope: float = 12.0) -> str:
    """Un enlace de un solo uso hacia esa misma pantalla, o cadena VACIA si no se ha podido.

    La cadena vacia significa "abre el de siempre", y por eso no lanza: quien llama no tiene que
    decidir nada, solo usar lo que devuelva o lo que ya tenia.
    """
    sistema = de_quien_es(url)
    if not sistema or not CLAVE:
        return ""
    cuerpo = json.dumps({"destino": _ruta(url)}).encode()
    req = urllib.request.Request(
        DENTRO[sistema].rstrip("/") + "/auth/entrada", data=cuerpo, method="POST",
        headers={"Content-Type": "application/json", "X-Zeno-Key": CLAVE})
    try:
        with urllib.request.urlopen(req, timeout=tope) as r:
            datos = json.loads(r.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        # Sistema caido, clave retirada, o una version que todavia no tiene este endpoint. Las
        # tres se resuelven igual: el enlace de siempre.
        return ""
    salida = str(datos.get("url") or "")
    # LO QUE VUELVE TAMBIEN SE COMPRUEBA. Si el sistema devolviera una direccion de otro dominio,
    # Zeno estaria mandando al operador fuera con la confianza de haberlo abierto el.
    return salida if de_quien_es(salida) == sistema else ""
