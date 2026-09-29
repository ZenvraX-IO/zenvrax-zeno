# -*- coding: utf-8 -*-
"""El envio de correo, contra Gmail de verdad, a la propia direccion del operador.

POR QUE EXISTE. Enviar es la segunda cosa de Zeno que llega a una persona, despues de publicar, y
las barreras (PIN, vale de un solo uso, diario, nada por voz) estan probadas con tests. Lo que NO
puede probar un test es que Gmail acepte la peticion: el permiso concedido es `gmail.compose`, que
Google describe como *"Manage drafts and send emails"*, y de si eso alcanza para `drafts/send`
depende que el boton funcione o de un 403 delante del operador.

NO SALE HACIA NADIE. El destinatario es la propia direccion del operador. Es un correo suyo a si
mismo, que se borra.

MODO ENSAYO POR DEFECTO. Sin `--hazlo` dice a quien iria y que texto, y no manda nada.

NO PASA POR EL PIN, y se dice a proposito: aqui no hay sesion, asi que se llama a `correo.envia()`
directamente. La barrera del PIN esta comprobada aparte, contra produccion: `POST /api/correo/enviar`
sin PIN devuelve 428 con el mensaje "enviar un correo no se deshace: hace falta el PIN".
"""
from __future__ import annotations

import base64
import sys
from email.message import EmailMessage

sys.path.insert(0, "/app")
from servicio import correo, google  # noqa: E402

HAZLO = "--hazlo" in sys.argv
ENSAYO = not HAZLO

ASUNTO = "Zeno: prueba de envio (29-sep), se puede borrar"
CUERPO = (
    "Esto lo ha enviado Zeno desde el movil para comprobar que el envio de correo funciona de\n"
    "verdad contra Gmail, no solo en los tests.\n\n"
    "No ha salido hacia nadie mas: va a tu propia direccion. Se puede borrar.\n")


def main() -> int:
    destino = google.CUENTAS["zenvrax"]
    print(f"destinatario : {destino}  (la tuya)")
    print(f"asunto       : {ASUNTO}")
    print(f"permiso      : {google.PERMISO_BORRADOR}")
    print(f"modo         : {'ENVIA DE VERDAD' if HAZLO else 'ENSAYO (no manda nada)'}")
    print()

    if ENSAYO:
        print("Se crearia el borrador en Gmail y despues se mandaria con drafts/send.")
        print("Coste: 0 USD. Ninguna llamada a Anthropic; dos llamadas a Gmail, que son gratis.")
        print("ensayo: nada se ha enviado. Con --hazlo se manda.")
        return 0

    # El camino REAL, el mismo que usa el boton: crear el borrador y mandarlo. No se replica a mano
    # la peticion, se llama al modulo, porque lo que hay que probar es el codigo que corre en
    # produccion y no una version parecida.
    m = EmailMessage()
    m["To"] = destino
    m["Subject"] = ASUNTO
    m.set_content(CUERPO)
    cuerpo = {"message": {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}}
    try:
        borrador = google.escribe("zenvrax", f"{correo.GMAIL}/drafts", cuerpo)
    except Exception as e:                                # noqa: BLE001
        print("NO se ha podido crear el borrador:", type(e).__name__, str(e)[:300])
        return 1
    ident = borrador.get("id", "")
    print("borrador creado:", ident or "(sin id)")
    if not ident:
        return 1

    try:
        google.escribe("zenvrax", f"{correo.GMAIL}/drafts/send", {"id": ident})
    except Exception as e:                                # noqa: BLE001
        # Este es el caso que importa: si el permiso no alcanzara, aqui saldria un 403 y el borrador
        # quedaria en Gmail. El operador sabria que le falta autorizar `gmail.send`.
        print("EL BORRADOR ESTA EN GMAIL pero NO se ha podido enviar:",
              type(e).__name__, str(e)[:300])
        return 1

    print("ENVIADO. Mira en Enviados.")
    return 0


sys.exit(main())
