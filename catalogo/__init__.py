# -*- coding: utf-8 -*-
"""El catalogo de acciones del asistente: lo que puede hacer, y nada mas.

Se arma juntando dos mitades que no pueden separarse:

  · `recolector`  lee del ARBOL de las dos colas el destino, el verbo y el cuerpo de cada boton
  · `metadatos`   declara a mano lo que el codigo no dice: si publica, si se deshace, si cuesta

`catalogo()` falla si una accion no tiene contrato. Esa es toda la idea de la fase J1: con 190 rutas
que mutan solo en el cockpit, un asistente que se deja elegir la llamada acaba adivinando, y adivinar
contra produccion se paga. Aqui no hay nada que adivinar: o la accion esta declarada o no existe.

USO:
    from catalogo import catalogo, ejecutables
    for a in ejecutables():
        print(a.op, a.efecto, a.verbo, a.destino)
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

from .contrato import ABRE, CAMBIA_ESTADO, PUBLICA, Contrato
from .metadatos import CONTRATOS
from .recolector import COLAS, clave, recolecta, sistemas_ausentes

__all__ = ["Accion", "catalogo", "ejecutables", "sin_contrato", "contratos_huerfanos",
           "ABRE", "CAMBIA_ESTADO", "PUBLICA", "Contrato", "sistemas_ausentes"]


@dataclass(frozen=True)
class Accion:
    """Una accion con sus dos mitades ya unidas."""
    op: str
    que_hace: str
    sistema: str
    efecto: str
    reversible: bool
    coste_api: bool
    confirmar: bool
    guarda: str
    verbo: str
    destino: str
    cuerpo: dict
    etiqueta: str
    linea: int
    #: El tramo de ruta que dice SI SE HIZO. Vacio = ese sistema no sabe contestarlo.
    #: VA AL FINAL Y CON DEFECTO a proposito: el contenedor arranca del catalogo CONGELADO,
    #: y un congelado escrito antes de que este campo existiera tiene que seguir cargando.
    #: Un campo nuevo no puede dejar a Zeno sin catalogo.
    comprobar: str = ""

    @property
    def muta(self) -> bool:
        return self.efecto != ABRE


class AccionSinContrato(RuntimeError):
    """Hay un boton nuevo en una cola que nadie ha declarado.

    Se lanza en vez de omitir la accion a proposito: omitirla dejaria al asistente creyendo que no
    existe, y el operador la veria en la aplicacion y no en el asistente, sin saber por que.
    """


def _del_congelado() -> list[Accion]:
    """El catalogo que viaja DENTRO de la imagen de Zeno.

    En el contenedor no estan los dos repos, asi que no se puede recolectar: sin esto, Zeno saldria
    con cero acciones y marcaria TODOS los botones "sin contrato", que es peor que no marcar nada
    porque parece un fallo del sistema y no una falta de datos.
    """
    fichero = pathlib.Path(__file__).resolve().parent / "congelado.json"
    if not fichero.exists():
        return []
    datos = json.loads(fichero.read_text(encoding="utf-8"))
    return [Accion(**a) for a in datos.get("acciones", [])]


def catalogo(sistemas=None) -> list[Accion]:
    """Todas las acciones con contrato. Lanza si alguna no lo tiene.

    Si NINGUN repo esta presente (o sea, se esta ejecutando dentro del contenedor), se usa el
    catalogo congelado. Fuera de ahi se recolecta de verdad, para que un boton nuevo se vea al
    momento en el disco del operador.
    """
    if len(sistemas_ausentes()) == len(COLAS) and not sistemas:
        return _del_congelado()
    fuera, faltan = [], []
    for accion in recolecta(sistemas):
        k = clave(accion)
        c = CONTRATOS.get(k)
        if c is None:
            faltan.append(k)
            continue
        fuera.append(Accion(
            op=c.op, que_hace=c.que_hace, sistema=accion["sistema"], efecto=c.efecto,
            reversible=c.reversible, coste_api=c.coste_api, confirmar=c.confirmar,
            guarda=c.guarda, comprobar=getattr(c, "comprobar", ""),
            verbo=accion["verbo"], destino=accion["destino"], cuerpo=accion["cuerpo"] or {},
            etiqueta=accion["etiqueta"], linea=accion["linea"]))
    if faltan:
        raise AccionSinContrato(
            "hay %d accion(es) en las colas sin contrato declarado en metadatos.py:\n  %s"
            % (len(faltan), "\n  ".join(faltan)))
    return fuera


def ejecutables(sistemas=None) -> list[Accion]:
    """Solo las que escriben algo. Las 13 que solo abren una pantalla no son acciones del asistente:
    son enlaces, y ofrecerlas como accion haria que confirmar perdiera sentido."""
    return [a for a in catalogo(sistemas) if a.muta]


def sin_contrato(sistemas=None) -> list[str]:
    """Las claves sin contrato, sin lanzar. Para que un test diga CUALES faltan."""
    return [clave(a) for a in recolecta(sistemas) if clave(a) not in CONTRATOS]


def contratos_huerfanos(sistemas=None) -> list[str]:
    """Contratos que ya no corresponden a ningun boton.

    Importa tanto como el caso contrario: un contrato huerfano significa que el boton cambio de
    destino o de etiqueta, asi que el asistente se quedo sin esa accion Y arrastra la descripcion de
    algo que ya no existe. Solo tiene sentido con los dos sistemas presentes.
    """
    if sistemas or sistemas_ausentes():
        return []
    vivas = {clave(a) for a in recolecta()}
    return sorted(k for k in CONTRATOS if k not in vivas)
