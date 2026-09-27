# -*- coding: utf-8 -*-
"""La ronda: mira si ha pasado algo que merezca interrumpir, y si lo hay, avisa.

    docker exec zeno-api python -m servicio.ronda

Va por cron y no dentro del servicio web a propósito. Un hilo de fondo dentro de la aplicación se
duplica cuando el servidor arranca varios procesos, sigue corriendo cuando el contenedor se está
apagando, y no deja rastro de cuándo corrió. Un cron se ve en `crontab -l`, escribe en su log y se
puede lanzar a mano para probarlo, que es lo que se acaba necesitando.

QUÉ MIRA. Lo mismo que la pantalla de la mañana, porque si avisara de algo que luego no aparece al
abrir Zeno, el operador dejaría de fiarse de las dos cosas. La diferencia está en el filtro, que
vive en `avisos.py`: la pantalla enseña todo, la ronda solo interrumpe por lo nuevo y lo que empeora.

NO GASTA API. La ronda no escribe texto con un modelo: junta lo que ya se lee y manda un aviso
corto. El resumen escrito es una cosa de la mañana y se paga una vez al día.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import lector                                          # noqa: E402
from servicio import avisos, empuje                    # noqa: E402


def candidatos() -> tuple[list[dict], list[str]]:
    """Todo lo que PODRIA avisar. Quien decide si suena es `avisos.que_suena`."""
    fuera, fallos = [], []

    plan, f1 = lector.plan_del_dia()
    fallos += f1
    for u in plan.get("urgentes") or []:
        fuera.append({"tipo": "urgente", "negocio": "Zenvrax IO", "clave": u.get("titulo"),
                      "titulo": u.get("titulo"), "grave": True, "valor": None})

    alertas, f2 = lector.alertas()
    fallos += f2
    for a in alertas:
        # El valor se saca del texto para poder comparar si empeora. Si no hay numero, no pasa nada:
        # el aviso suena una vez y se calla, que es el comportamiento por defecto.
        valor = None
        for trozo in str(a.get("texto", "")).replace(":", " ").split():
            limpio = trozo.replace("$", "").replace(".", "").replace(",", ".").rstrip("%")
            try:
                valor = float(limpio)
                break
            except ValueError:
                continue
        fuera.append({"tipo": "alerta", "negocio": a.get("negocio"),
                      # La clave NO lleva el numero: el texto cambia cada dia y la identidad no.
                      "clave": str(a.get("texto", "")).split(":")[0],
                      "titulo": a.get("texto"), "grave": bool(a.get("grave")), "valor": valor})
    return fuera, fallos


def corre(seco: bool = False) -> dict:
    """Una ronda. Con `seco`, dice que sonaria y no manda nada ni marca nada como sonado."""
    lista, fallos = candidatos()
    if seco:
        return {"candidatos": [c["titulo"] for c in lista], "fallos": fallos, "seco": True}
    if not avisos.suscritos():
        return {"sin_suscriptores": True, "candidatos": len(lista), "fallos": fallos}

    suenan, _ = avisos.que_suena(lista)
    if not suenan:
        return {"nada_nuevo": True, "candidatos": len(lista), "fallos": fallos}

    mensaje = avisos.redacta(suenan)
    resultado = empuje.manda(mensaje)
    return {"aviso": mensaje, **resultado, "fallos": fallos}


if __name__ == "__main__":
    import json
    print(json.dumps(corre(seco="--seco" in sys.argv), ensure_ascii=False))
