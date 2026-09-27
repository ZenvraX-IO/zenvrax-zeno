# -*- coding: utf-8 -*-
"""Los avisos al móvil. Lo que hace que Zeno hable primero en vez de esperar a que lo abras.

LA REGLA QUE DECIDE TODO AQUÍ: un aviso que se ignora vale menos que ninguno. En cuanto suenan dos
que no hacían falta, se dejan de mirar los que sí, y entonces el sistema es peor que antes de
tenerlos. Así que esto está montado al revés de lo normal: la pregunta no es qué se puede avisar,
sino qué merece interrumpir.

Lo que avisa, y nada más:

  · Lo que el cockpit marca URGENTE y no estaba marcado ayer.
  · Lo que se pone en rojo (`bad`), como el beneficio del mes en negativo.
  · Un aviso en ámbar solo si el número EMPEORA. Los 57 signups sin contactar llevan ahí días: el
    día que sean 80 es noticia, que sigan siendo 57 no lo es.

Lo que NO avisa, a propósito:

  · Nada que ya sonó. Cada aviso tiene una clave fija, y una clave suena una vez.
  · Nada en verde. Ocho semáforos en verde no son información.
  · Nada por acumulación: si hay diez cosas nuevas, es UN aviso que dice diez, no diez avisos.

CÓMO LLEGA. Web Push del navegador, o sea al móvil y con la aplicación cerrada. No es Slack ni
Telegram: el operador pidió puerta propia (2026-09-27) y un aviso que llega por la casa de otro
convierte a Zeno en una notificación más de esa casa.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

#: Donde se guardan las suscripciones del navegador y lo que ya sonó. Mismo volumen que el cofre,
#: porque tiene el mismo problema: si no persiste, cada reinicio deja al operador sin avisos y
#: encima le vuelve a sonar todo lo de ayer.
CASA = pathlib.Path(os.environ.get("ZENO_AVISOS", "/datos/avisos.json"))

#: Cuánto calla una clave que ya sonó. Tres días: lo bastante para no repetir una tarea urgente que
#: sigue ahí, y lo bastante poco para que algo que vuelve dentro de una semana avise otra vez.
SILENCIO = 3 * 24 * 3600

#: Tope de avisos al día. Es la última red: si algo se rompe y empieza a generar avisos, el operador
#: recibe cinco y no cincuenta.
TOPE_DIARIO = int(os.environ.get("ZENO_TOPE_AVISOS", "5"))


def _lee() -> dict:
    if not CASA.exists():
        return {"suscripciones": [], "sonados": {}, "contador": {}}
    try:
        d = json.loads(CASA.read_text(encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        # Un fichero a medias no puede dejar a Zeno sin avisar: se empieza de cero y como mucho
        # suena otra vez algo de ayer, que es mucho menos malo que quedarse mudo.
        return {"suscripciones": [], "sonados": {}, "contador": {}}
    d.setdefault("suscripciones", [])
    d.setdefault("sonados", {})
    d.setdefault("contador", {})
    return d


def _guarda(d: dict) -> None:
    CASA.parent.mkdir(parents=True, exist_ok=True)
    CASA.write_text(json.dumps(d), encoding="utf-8")


def apunta(suscripcion: dict) -> int:
    """Guarda un navegador que quiere avisos. Devuelve cuantos hay."""
    d = _lee()
    punto = suscripcion.get("endpoint")
    if not punto:
        raise ValueError("la suscripcion no trae endpoint")
    # Por endpoint: el mismo movil suscrito dos veces recibiria el aviso dos veces.
    d["suscripciones"] = [s for s in d["suscripciones"] if s.get("endpoint") != punto]
    d["suscripciones"].append(suscripcion)
    _guarda(d)
    return len(d["suscripciones"])


def olvida(punto: str) -> bool:
    d = _lee()
    antes = len(d["suscripciones"])
    d["suscripciones"] = [s for s in d["suscripciones"] if s.get("endpoint") != punto]
    _guarda(d)
    return len(d["suscripciones"]) < antes


def suscritos() -> int:
    return len(_lee()["suscripciones"])


# ---------------------------------------------------------------- que merece sonar

def _clave(a: dict) -> str:
    """La identidad de un aviso, sin el numero.

    Fija a proposito: si la clave llevara el valor, "57 signups" y "58 signups" serian dos avisos
    distintos y sonaria cada dia. Ya paso en esta casa con una alerta que solo debia sonar una vez.
    """
    return f"{a.get('tipo')}|{a.get('negocio','')}|{a.get('clave') or a.get('titulo','')}"[:160]


def _empeora(a: dict, antes: dict) -> bool:
    """Si un aviso en ambar que ya sono ha ido a peor. Solo entonces vuelve a sonar."""
    valor, previo = a.get("valor"), antes.get("valor")
    if valor is None or previo is None:
        return False
    try:
        return float(valor) > float(previo) * 1.2       # un 20% peor, no cualquier temblor
    except (TypeError, ValueError):
        return False


def que_suena(candidatos: list[dict], ahora: float | None = None) -> tuple[list[dict], dict]:
    """De todo lo que podria avisar, lo que de verdad suena. Devuelve (los que suenan, estado nuevo).

    Es una funcion pura sobre el estado guardado: se puede probar entera sin red y sin navegador,
    que es lo que hace falta para fiarse de algo que decide cuando interrumpir a una persona.
    """
    ahora = time.time() if ahora is None else ahora
    d = _lee()
    sonados = {k: v for k, v in d["sonados"].items() if ahora - v.get("cuando", 0) < SILENCIO}
    hoy = time.strftime("%Y-%m-%d", time.gmtime(ahora))
    ya_hoy = d["contador"].get(hoy, 0)

    suenan = []
    for a in candidatos:
        k = _clave(a)
        antes = sonados.get(k)
        if antes and not (a.get("grave") and not antes.get("grave")) and not _empeora(a, antes):
            continue
        suenan.append(a)
        sonados[k] = {"cuando": ahora, "valor": a.get("valor"), "grave": bool(a.get("grave"))}

    if ya_hoy + (1 if suenan else 0) > TOPE_DIARIO:
        # El tope cuenta ENVIOS, no avisos: como todo va en un solo mensaje, pasar del tope
        # significa que hoy ya ha sonado demasiado y lo de ahora espera a mañana. Se marcan como
        # sonados igual, para que mañana no llegue el atasco entero de golpe.
        _guarda({**d, "sonados": sonados})
        return [], {**d, "sonados": sonados}

    if suenan:
        d["contador"] = {hoy: ya_hoy + 1}               # solo el de hoy: el de ayer no sirve
    d["sonados"] = sonados
    _guarda(d)
    return suenan, d


def redacta(suenan: list[dict]) -> dict:
    """Un solo mensaje con todo lo que suena. Diez cosas nuevas son UN aviso que dice diez."""
    graves = [a for a in suenan if a.get("grave")]
    cabeza = suenan[0]
    if len(suenan) == 1:
        titulo = "Zeno" if not cabeza.get("grave") else "Zeno, algo va mal"
        cuerpo = cabeza.get("titulo", "")
    else:
        titulo = f"Zeno: {len(suenan)} cosas nuevas"
        if graves:
            titulo = f"Zeno: {len(graves)} grave{'s' if len(graves) > 1 else ''} y mas"
        cuerpo = " · ".join(a.get("titulo", "") for a in suenan[:3])
        if len(suenan) > 3:
            cuerpo += f" y {len(suenan) - 3} mas"
    return {"titulo": titulo, "cuerpo": cuerpo[:180], "url": "/"}
