# -*- coding: utf-8 -*-
"""Lo que Zeno ha hecho. Un renglón por cada cosa que salió de aquí.

POR QUÉ EXISTE, y es un hueco que abrí yo esta misma tarde. Con J4, Zeno pasó a publicar en nombre
del operador y no dejaba rastro por su lado: el post aparecía en LinkedIn y el único sitio donde
constaba era el sistema de destino, mezclado con lo que aprueba el cockpit y lo que aprueba Xrise.

Las tres preguntas que esto contesta y antes no tenían respuesta:

  · **"¿Esto lo he aprobado yo desde Zeno o fue otra cosa?"** La primera que se hace uno cuando ve
    algo publicado que no recuerda.
  · **"¿Salió o no salió?"** Cuando una confirmación acaba en timeout, Zeno dice que no lo sabe. El
    renglón queda escrito igualmente, marcado como dudoso, porque un intento del que no se sabe el
    resultado es justo el que hay que ir a mirar.
  · **"¿Qué he hecho hoy?"** El `done_today` del cockpit no vale para esto: son accesos a la
    aplicación, no trabajo.

CÓMO SE GUARDA. Un fichero de líneas, en el mismo volumen que el cofre, y se añade al final sin
leer lo anterior: escribir un renglón no puede fallar porque el fichero sea grande ni porque otra
escritura esté a medias. Se recorta cuando pasa de mil, que son meses de uso.

LO QUE NO GUARDA: el cuerpo de lo publicado. Zeno no es el sitio donde vive el contenido, y una
copia sería la tercera verdad que esta arquitectura evita a propósito. Se guarda qué acción, sobre
qué, cuándo y cómo acabó.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

LIBRO = pathlib.Path(os.environ.get("ZENO_DIARIO", "/datos/hecho.jsonl"))
#: Cuantos renglones se conservan. Mil son meses: lo viejo no ayuda a contestar ninguna de las tres
#: preguntas de arriba, y un fichero que crece sin fin acaba siendo un problema de disco.
TOPE = 1000


def apunta(que: dict) -> None:
    """Escribe un renglon. NUNCA lanza: que el diario falle no puede tumbar una accion ya hecha."""
    try:
        LIBRO.parent.mkdir(parents=True, exist_ok=True)
        renglon = {"cuando": time.time(), **que}
        crudo = (json.dumps(renglon, ensure_ascii=False) + "\n").encode("utf-8")
        with LIBRO.open("ab") as f:
            # SI LA ULTIMA LINEA QUEDO A MEDIAS, se cierra antes de escribir. Lo encontro un test:
            # si un reinicio corto una escritura y no dejo el salto de linea, el renglon siguiente
            # se pegaba al roto y se perdian LOS DOS. Una linea rota solo puede costar una linea.
            if f.tell():
                with LIBRO.open("rb") as previo:
                    previo.seek(-1, 2)
                    if previo.read(1) != b"\n":
                        f.write(b"\n")
            f.write(crudo)
    except Exception:                                    # noqa: BLE001
        # Si esto reventara despues de publicar, el operador veria un error y creeria que no salio,
        # cuando si salio. El diario es para mirar despues; la accion ya esta hecha.
        pass


def lee(cuantos: int = 40) -> list[dict]:
    """Los ultimos renglones, del mas reciente al mas viejo."""
    if not LIBRO.exists():
        return []
    try:
        lineas = LIBRO.read_text(encoding="utf-8").splitlines()
    except Exception:                                    # noqa: BLE001
        return []
    fuera = []
    for linea in reversed(lineas[-TOPE:]):
        try:
            fuera.append(json.loads(linea))
        except Exception:                                # noqa: BLE001
            # Una linea a medias (un reinicio en mitad de la escritura) se salta. Tirar el fichero
            # entero por un renglon roto seria perder el historial por nada.
            continue
        if len(fuera) >= cuantos:
            break
    return fuera


def recorta() -> int:
    """Deja el libro en el tope. Devuelve cuantos renglones quedan."""
    if not LIBRO.exists():
        return 0
    try:
        lineas = LIBRO.read_text(encoding="utf-8").splitlines()
    except Exception:                                    # noqa: BLE001
        return 0
    if len(lineas) <= TOPE:
        return len(lineas)
    LIBRO.write_text("\n".join(lineas[-TOPE:]) + "\n", encoding="utf-8")
    return TOPE
