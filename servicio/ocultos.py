# -*- coding: utf-8 -*-
"""Lo que el operador ha quitado de en medio en Zeno, sin tocar Gmail.

EL CASO (2026-09-29). Pregunto si se podia borrar correo desde Zeno. Medido: no, el permiso
concedido (`gmail.readonly` + `gmail.compose`) no deja ni mover a la papelera ni archivar; haria
falta autorizar `gmail.modify`. Y al ponerle las opciones delante, aclaro lo que de verdad queria:

    *"Lo unico es no verlo en Zeno, aun cuando siga en Gmail."*

Eso NO NECESITA NINGUN PERMISO NUEVO. Es una lista de Zeno, en el volumen de Zeno, con los ids de
lo que no quiere volver a ver aqui. El correo sigue intacto en su buzon, sin leer, y Gmail no se
entera de nada.

POR QUE ES MEJOR QUE PEDIR `gmail.modify`. Una llave que puede archivar y tirar a la papelera es
una llave que puede equivocarse con el correo de verdad. Esta lista, si se borra entera, solo hace
que vuelvan a verse unos correos. El peor caso de las dos cosas no se parece.

MISMO PATRON QUE `notif_dismissed` en el cockpit, que lleva meses haciendo justo esto con los
avisos: esconder sin destruir. Lo que funciona no se reinventa.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

FICHERO = Path(os.environ.get("ZENO_OCULTOS", "/datos/correo_oculto.json"))

#: Cuanto se recuerda que algo esta oculto. La bandeja solo mira los ultimos siete dias, asi que a
#: los treinta ese correo ya no podria aparecer ni queriendo: guardarlo mas tiempo es una lista que
#: crece sin que nadie la lea.
DIAS = 30


def _lee() -> dict:
    try:
        d = json.loads(FICHERO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        # Ni fichero, ni JSON valido: la lista vacia es la respuesta correcta. Que esto falle no
        # puede dejar la bandeja sin pintar.
        return {}


def _guarda(d: dict) -> None:
    try:
        FICHERO.parent.mkdir(parents=True, exist_ok=True)
        FICHERO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def oculta(ident: str) -> bool:
    """Esconde un correo en Zeno. No toca Gmail."""
    ident = (ident or "").strip()
    if not ident:
        return False
    d = _lee()
    d[ident] = time.time()
    # La limpieza va aqui, al escribir, y no en un reloj aparte: una pieza que corre por su cuenta
    # es una pieza mas que puede dejar de correr sin que nadie se entere.
    corte = time.time() - DIAS * 86400
    _guarda({k: v for k, v in d.items() if isinstance(v, (int, float)) and v >= corte})
    return True


def saca(ident: str) -> bool:
    """Lo devuelve a la bandeja de Zeno. Es el deshacer de `oculta`."""
    d = _lee()
    if ident not in d:
        return False
    d.pop(ident, None)
    _guarda(d)
    return True


def vacia() -> int:
    """Devuelve TODOS a la bandeja. Cuantos vuelven."""
    d = _lee()
    _guarda({})
    return len(d)


def cuales() -> set[str]:
    """Los ids ocultos ahora mismo."""
    return set(_lee().keys())


def cuantos() -> int:
    return len(_lee())
