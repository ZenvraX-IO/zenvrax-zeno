# -*- coding: utf-8 -*-
"""Lo que el codigo de las colas NO puede decir de cada accion, declarado una vez.

El recolector saca del arbol el destino, el verbo y el cuerpo. Lo que no esta escrito en ninguna
parte, y es justo lo que un asistente necesita antes de ejecutar algo en nombre del operador, es:

  · `efecto`      publica (sale al mundo y no vuelve) · cambia_estado (interno) · abre (no muta nada)
  · `reversible`  si se puede deshacer despues
  · `coste_api`   si dispara una llamada de pago. Hay una regla dura sobre esto y el asistente
                  no puede saltarsela por no saber cual gasta
  · `confirmar`   si el asistente tiene que preguntar antes
  · `guarda`      que la protege HOY, y "ninguna" cuando no hay ninguna: es mas util saberlo

POR QUE A MANO Y NO ADIVINADO. Tres acciones de esta lista publican de verdad y estan escritas
EXACTAMENTE igual que un enlace a una guia en HTML (`url` con un webhook de n8n por GET). Nada en el
dato las distingue. Un recolector que dedujera el efecto del verbo diria que un GET no muta, y
publicaria en LinkedIn creyendo que abre una vista.

COMO SE MANTIENE. `metadatos.py` se indexa por la clave que produce el recolector, y el test falla si
aparece una accion sin contrato o un contrato que ya no corresponde a ninguna accion. Asi, quien
añada un boton a cualquiera de las dos colas tiene que declarar que hace, y hasta que lo haga el
asistente no lo ve. Medido el 2026-09-27: 33 acciones, 20 ejecutan y 13 solo abren.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Efectos posibles. Se quedan en tres a proposito: mas matices no cambiarian ninguna decision.
PUBLICA = "publica"              # sale al mundo (LinkedIn, X, Meta, correo). No se deshace
CAMBIA_ESTADO = "cambia_estado"  # mueve algo dentro del sistema
ABRE = "abre"                    # no escribe nada


@dataclass(frozen=True)
class Contrato:
    op: str
    que_hace: str
    efecto: str
    reversible: bool
    coste_api: bool = False
    confirmar: bool = field(default=True)
    guarda: str = "ninguna"

    def __post_init__(self):
        if self.efecto not in (PUBLICA, CAMBIA_ESTADO, ABRE):
            raise ValueError(f"efecto desconocido: {self.efecto}")
        if self.efecto == PUBLICA and self.reversible:
            raise ValueError(f"{self.op}: lo que sale al mundo no se declara reversible")
        if self.efecto == ABRE and self.confirmar:
            raise ValueError(f"{self.op}: abrir algo no se confirma, seria ruido en cada consulta")
