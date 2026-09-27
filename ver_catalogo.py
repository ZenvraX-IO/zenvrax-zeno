# -*- coding: utf-8 -*-
"""Imprime el catalogo de acciones del asistente. Solo lee ficheros: no toca red ni base de datos.

    python lab/zeno/ver_catalogo.py              # todo, agrupado por efecto
    python lab/zeno/ver_catalogo.py --ejecutan   # solo las 20 que escriben algo
    python lab/zeno/ver_catalogo.py --alcance    # que se ha podido validar y que no
    python lab/zeno/ver_catalogo.py --json       # para consumirlo desde otro sitio
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalogo as C                                       # noqa: E402
from catalogo.recolector import COLAS, RAICES, sistemas_ausentes   # noqa: E402

ORDEN = [(C.PUBLICA, "SALE AL MUNDO (no se deshace)"),
         (C.CAMBIA_ESTADO, "CAMBIA ESTADO (dentro del sistema)"),
         (C.ABRE, "SOLO ABRE (no escribe nada)")]


def _alcance() -> int:
    ausentes = sistemas_ausentes()
    print("  colas leidas:")
    for sistema, relativo in COLAS.items():
        fichero = RAICES[sistema] / relativo
        marca = "si" if fichero.exists() else "NO ESTA"
        print(f"     {sistema:8s} {marca:8s} {fichero}")
    if not ausentes:
        print("  los dos sistemas presentes: el catalogo se ha validado entero")
        return 0
    # Las acciones de un sistema ausente no se pueden comprobar. Se dice, en vez de dar por bueno
    # un catalogo validado a medias.
    declaradas = {}
    for k in C.metadatos.CONTRATOS:
        declaradas[k.split("|")[0]] = declaradas.get(k.split("|")[0], 0) + 1
    for s in ausentes:
        print(f"  SIN VALIDAR: las {declaradas.get(s, 0)} acciones de {s!r}, su repo no esta aqui")
    return 0


def main() -> int:
    if "--alcance" in sys.argv:
        return _alcance()
    acciones = C.ejecutables() if "--ejecutan" in sys.argv else C.catalogo()
    if "--json" in sys.argv:
        print(json.dumps([a.__dict__ for a in acciones], ensure_ascii=False, indent=1))
        return 0
    total, ejec = len(C.catalogo()), len(C.ejecutables())
    if len(acciones) == total:
        print(f"  {total} acciones · {ejec} escriben algo · {total - ejec} solo abren")
    else:
        print(f"  {len(acciones)} de {total} acciones: solo las que escriben algo")
    if sistemas_ausentes():
        print(f"  (faltan los repos de: {', '.join(sistemas_ausentes())})")
    for efecto, titulo in ORDEN:
        grupo = sorted((a for a in acciones if a.efecto == efecto), key=lambda x: x.op)
        if not grupo:
            continue
        print(f"\n  --- {titulo} · {len(grupo)} ---")
        for a in grupo:
            marcas = []
            if a.coste_api:
                marcas.append("CUESTA")
            if a.confirmar:
                marcas.append("confirmar")
            if a.guarda.startswith("ninguna"):
                marcas.append("sin guarda")
            print(f"   {a.sistema:8s} {a.op:34s} {a.verbo:6s} {str(a.destino)[:44]:44s} "
                  f"{' '.join(marcas)}")
            print(f"            {a.que_hace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
