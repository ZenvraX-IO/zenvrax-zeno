# -*- coding: utf-8 -*-
"""Deja el catálogo en un fichero, para que Zeno lo tenga dentro del contenedor.

POR QUE EXISTE. El catálogo se RECOLECTA leyendo el código de las dos colas, y eso solo funciona
donde están los dos repos: en el disco del operador o en el servidor. Dentro de la imagen de Zeno no
están, así que `catalogo()` devolvería cero acciones y Zeno perdería justo lo que aporta sobre mirar
las dos pantallas: saber si algo sale al mundo o cuesta dinero.

Se descubrió escribiendo el Dockerfile, no en producción, que es donde se habría notado: la lista de
pendientes habría salido con todos los botones marcados "sin contrato".

COMO SE USA. El fichero se GENERA, nunca se edita a mano:

    python lab/zeno/catalogo/congelar.py

Se commitea, y un test comprueba que sigue cuadrando con las colas. Así el desfase se ve en el CI y
no la primera noche que el operador mire el móvil.
"""
import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from catalogo import catalogo                       # noqa: E402
from catalogo.recolector import sistemas_ausentes   # noqa: E402

DESTINO = pathlib.Path(__file__).resolve().parent / "congelado.json"


def congela() -> dict:
    if sistemas_ausentes():
        raise SystemExit(
            "  faltan repos (%s): un catalogo congelado a medias es PEOR que ninguno, porque las "
            "acciones del sistema ausente saldrian marcadas 'sin contrato'."
            % ", ".join(sistemas_ausentes()))
    acciones = catalogo()
    return {
        "generado": date.today().isoformat(),
        "acciones": [a.__dict__ for a in acciones],
    }


if __name__ == "__main__":
    datos = congela()
    DESTINO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  {DESTINO.name}: {len(datos['acciones'])} acciones · {datos['generado']}")
