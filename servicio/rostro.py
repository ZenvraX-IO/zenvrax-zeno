# -*- coding: utf-8 -*-
"""Entrar con Face ID, o con la huella, en vez de escribir la clave.

EL CASO (2026-09-28). El operador: *"para poder entrar en la aplicacion con el Face ID fuera mas
que suficiente y no te estuviera pidiendo codigo o contraseña cada vez"*.

POR QUE LE PEDIA LA CLAVE. Medido: el token dura 90 dias y su firma no cambia al reiniciar el
servicio, asi que el servidor no lo estaba echando. Lo que se pierde es el almacenamiento del
navegador, que iOS purga. Una passkey NO vive ahi: vive en el llavero, sobrevive a las purgas y
viaja a los demas dispositivos de la cuenta. Por eso esto arregla el problema de raiz y guardar
la clave "mas tiempo" no lo habria arreglado.

QUE ES Y QUE NO ES. Es WebAuthn de verdad, con firma comprobada en el servidor: un reto de un
solo uso, la firma verificada contra la clave publica que se guardo al dar de alta, y el contador
del autenticador. NO es "Face ID para desbloquear un token guardado", que es lo comodo de montar
y no demuestra nada: ahi quien copie el almacenamiento del navegador entra igual.

La cara NUNCA sale del telefono. Apple no la manda a ningun sitio: el movil comprueba que eres tu
y solo entonces firma con una clave privada que tampoco sale de su chip. Aqui llega la firma.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

import webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

#: De donde cuelga la aplicacion. TIENE QUE SER EL DOMINIO, sin esquema ni puerto: si aqui pone
#: "https://zeno.zenvrax.com", el navegador rechaza el alta sin decir por que.
DOMINIO = os.environ.get("ZENO_DOMINIO", "zeno.zenvrax.com")
ORIGEN = os.environ.get("ZENO_URL_PUBLICA", "https://zeno.zenvrax.com").rstrip("/")
NOMBRE = "Zeno"

FICHERO = Path(os.environ.get("ZENO_ROSTROS", "/datos/rostros.json"))

#: Cuanto vive un reto. Corto a proposito: es de un solo uso y solo tiene que durar lo que tarda
#: una cara en mirar un telefono.
VIVE_RETO = 120.0

#: Retos entregados y todavia sin usar. En memoria: si el servicio se reinicia, el reto se pierde
#: y se pide otro, que es exactamente lo que debe pasar.
_RETOS: dict[str, float] = {}


class NoVale(RuntimeError):
    """El Face ID no ha valido, y el mensaje dice por que."""


# ------------------------------------------------------------------ lo guardado

def _lee() -> dict:
    try:
        return json.loads(FICHERO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"caras": []}


def _guarda(d: dict) -> None:
    FICHERO.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHERO.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FICHERO)          # atomico: un corte a medias no deja el fichero roto


def cuantas() -> int:
    return len(_lee().get("caras") or [])


def hay() -> bool:
    return cuantas() > 0


def olvidar(ident: str = "") -> int:
    """Quita una cara, o todas si no se dice cual. Devuelve cuantas quedan.

    Existe desde el primer dia y no "cuando haga falta": una credencial que se puede dar de alta y
    no de baja es una llave que no se puede cambiar.
    """
    d = _lee()
    antes = d.get("caras") or []
    d["caras"] = [c for c in antes if ident and c["id"] != ident] if ident else []
    _guarda(d)
    return len(d["caras"])


# ------------------------------------------------------------------ dar de alta una cara

def _reto() -> bytes:
    ahora = time.time()
    for r, nacido in list(_RETOS.items()):
        if ahora - nacido > VIVE_RETO:
            _RETOS.pop(r, None)
    crudo = secrets.token_bytes(32)
    _RETOS[bytes_to_base64url(crudo)] = ahora
    return crudo


def _quema(reto_b64: str) -> None:
    """Un reto vale UNA vez. Sin esto, quien grabara una respuesta podria repetirla."""
    nacido = _RETOS.pop(reto_b64, None)
    if nacido is None:
        raise NoVale("ese intento ya se ha usado o ha caducado")
    if time.time() - nacido > VIVE_RETO:
        raise NoVale("ese intento ha caducado")


def alta_empieza(correo: str) -> dict:
    """Lo que el navegador necesita para pedirle la cara al telefono y crear la llave."""
    opciones = webauthn.generate_registration_options(
        rp_id=DOMINIO,
        rp_name=NOMBRE,
        user_name=correo or "operador",
        user_display_name=correo or "operador",
        challenge=_reto(),
        # Los ids de lo que ya esta dado de alta, para que el telefono no cree una llave repetida.
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
                             for c in _lee().get("caras") or []],
        authenticator_selection=AuthenticatorSelectionCriteria(
            # La llave se queda EN EL TELEFONO (o en el llavero), no en una memoria externa, y
            # exige comprobar que eres tu: sin `required`, un telefono podria firmar solo con
            # estar desbloqueado, y entonces esto no seria Face ID, seria "tener el movil".
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return json.loads(webauthn.options_to_json(opciones))


def alta_termina(respuesta: dict, apodo: str = "") -> dict:
    """Comprueba lo que devolvio el telefono y guarda la clave publica."""
    reto = (respuesta.get("response") or {}).get("clientDataJSON")
    if not reto:
        raise NoVale("la respuesta del teléfono viene incompleta")
    import base64
    datos = json.loads(base64.urlsafe_b64decode(reto + "=" * (-len(reto) % 4)))
    _quema(datos.get("challenge", ""))
    try:
        v = webauthn.verify_registration_response(
            credential=respuesta,
            expected_challenge=base64url_to_bytes(datos["challenge"]),
            expected_rp_id=DOMINIO,
            expected_origin=ORIGEN,
            require_user_verification=True,
        )
    except Exception as e:                       # la libreria lanza de varios tipos
        raise NoVale(f"no he podido comprobarlo: {e}") from e

    d = _lee()
    caras = [c for c in (d.get("caras") or []) if c["id"] != bytes_to_base64url(v.credential_id)]
    caras.append({
        "id": bytes_to_base64url(v.credential_id),
        "clave": bytes_to_base64url(v.credential_public_key),
        "contador": v.sign_count,
        "apodo": (apodo or "este teléfono")[:40],
        "cuando": time.time(),
    })
    _guarda({**d, "caras": caras})
    return {"alta": True, "apodo": caras[-1]["apodo"], "cuantas": len(caras)}


# ------------------------------------------------------------------ entrar con la cara

def entrada_empieza() -> dict:
    if not hay():
        raise NoVale("no hay ningún Face ID dado de alta")
    opciones = webauthn.generate_authentication_options(
        rp_id=DOMINIO,
        challenge=_reto(),
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
                           for c in _lee()["caras"]],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return json.loads(webauthn.options_to_json(opciones))


def entrada_termina(respuesta: dict) -> dict:
    """Comprueba la firma. Si vale, quien llama puede emitir la sesion.

    Este modulo NO emite el token a proposito: emitir sesiones es de `clave.py`, que es donde
    estan la duracion y la firma. Dos sitios que emiten sesiones son dos sitios que caducan
    distinto.
    """
    import base64
    cruda = (respuesta.get("response") or {}).get("clientDataJSON")
    if not cruda:
        raise NoVale("la respuesta del teléfono viene incompleta")
    datos = json.loads(base64.urlsafe_b64decode(cruda + "=" * (-len(cruda) % 4)))
    _quema(datos.get("challenge", ""))

    d = _lee()
    ident = respuesta.get("id") or respuesta.get("rawId") or ""
    cara = next((c for c in d.get("caras") or [] if c["id"] == ident), None)
    if not cara:
        raise NoVale("ese teléfono no está dado de alta")
    try:
        v = webauthn.verify_authentication_response(
            credential=respuesta,
            expected_challenge=base64url_to_bytes(datos["challenge"]),
            expected_rp_id=DOMINIO,
            expected_origin=ORIGEN,
            credential_public_key=base64url_to_bytes(cara["clave"]),
            credential_current_sign_count=cara.get("contador", 0),
            require_user_verification=True,
        )
    except Exception as e:
        raise NoVale(f"el Face ID no ha valido: {e}") from e

    # El contador solo sube. Si baja, hay una copia de la llave por ahi y eso se avisa, no se
    # ignora. Las passkeys del llavero de Apple lo dejan a cero siempre: solo se comprueba cuando
    # el autenticador de verdad lo usa.
    if v.new_sign_count and v.new_sign_count <= cara.get("contador", 0):
        raise NoVale("ese teléfono ha firmado con un contador viejo: revísalo")
    cara["contador"] = v.new_sign_count
    cara["ultima"] = time.time()
    _guarda(d)
    return {"vale": True, "apodo": cara["apodo"]}
