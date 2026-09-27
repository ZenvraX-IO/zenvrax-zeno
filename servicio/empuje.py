# -*- coding: utf-8 -*-
"""Mandar el aviso al móvil de verdad. La parte que habla con el navegador.

QUÉ ES WEB PUSH y por qué no es Slack. El navegador guarda una suscripción con una clave suya, y
solo acepta mensajes firmados con la clave VAPID de Zeno y cifrados para él. Ni Google ni Apple, que
son quienes transportan el aviso, pueden leer el contenido. Eso es lo que permite que un aviso diga
"Beneficio del mes en negativo" sin que esa frase pase en claro por la casa de nadie.

Y es la puerta propia que pidió el operador: llega a la aplicación de Zeno instalada en el móvil, no
a un canal de un tercero.

LO QUE HAY QUE SABER PARA QUE FUNCIONE:

  · **El móvil tiene que tener la aplicación INSTALADA.** En iOS, una pestaña de Safari no recibe
    avisos; la PWA añadida a la pantalla de inicio sí. En Android y en el escritorio basta con dar
    permiso.
  · **Una suscripción caduca sola.** El navegador la rota, o el operador desinstala. Cuando el
    servicio de empuje contesta 404 o 410, esa suscripción está muerta y se borra: reintentar contra
    ella para siempre llenaría el registro de errores que no son errores.
"""
from __future__ import annotations

import json
import os

from servicio import avisos

#: Las dos mitades de la llave VAPID. La publica la ve el navegador al suscribirse; la privada vive
#: en el `.env` del servidor y firma cada aviso. Sin ellas no se puede mandar nada, y se dice.
VAPID_PUBLICA = os.environ.get("ZENO_VAPID_PUBLICA", "")
VAPID_PRIVADA = os.environ.get("ZENO_VAPID_PRIVADA", "")
#: A quien escribir si un servicio de empuje tiene un problema con nuestros envios. Lo exige el
#: estandar; no se usa para nada mas.
VAPID_CONTACTO = os.environ.get("ZENO_VAPID_CONTACTO", "mailto:hola@zenvrax.com")


class SinLlaves(RuntimeError):
    """No hay llave VAPID configurada. Se dice, en vez de fallar callando en cada ronda."""


def configurado() -> bool:
    return bool(VAPID_PUBLICA and VAPID_PRIVADA)


def manda(mensaje: dict) -> dict:
    """Manda un aviso a todos los navegadores suscritos. Devuelve cuantos y cuantos murieron."""
    if not configurado():
        raise SinLlaves("faltan ZENO_VAPID_PUBLICA y ZENO_VAPID_PRIVADA")
    from pywebpush import WebPushException, webpush        # noqa: PLC0415

    d = avisos._lee()
    enviados, muertos, fallos = 0, [], []
    for s in d["suscripciones"]:
        try:
            webpush(subscription_info=s, data=json.dumps(mensaje),
                    vapid_private_key=VAPID_PRIVADA,
                    vapid_claims={"sub": VAPID_CONTACTO}, timeout=15)
            enviados += 1
        except WebPushException as e:
            codigo = getattr(getattr(e, "response", None), "status_code", 0)
            if codigo in (404, 410):
                # La suscripcion esta muerta: el navegador la roto o se desinstalo la aplicacion.
                # Reintentar contra ella para siempre llenaria el log de errores que no lo son.
                muertos.append(s.get("endpoint"))
            else:
                fallos.append(f"{codigo or type(e).__name__}")
        except Exception as e:                               # noqa: BLE001
            fallos.append(type(e).__name__)

    for punto in muertos:
        avisos.olvida(punto)
    return {"enviados": enviados, "caducados": len(muertos), "fallos": fallos}
