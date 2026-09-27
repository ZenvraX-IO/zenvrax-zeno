# -*- coding: utf-8 -*-
"""Zeno por linea de ordenes. Solo LEE: no ejecuta ninguna accion.

    python lab/zeno/zeno.py pendientes          # lo que espera tu OK, de los dos negocios
    python lab/zeno/zeno.py estado              # como van los dos negocios
    python lab/zeno/zeno.py busca <texto>       # que dice la documentacion
    python lab/zeno/zeno.py todo                # las tres cosas de un tiron

Necesita `ZENO_READ_KEY` en el entorno. Cero llamadas a APIs de pago: solo GET al cockpit y a Xrise.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalogo as C          # noqa: E402
import lector                 # noqa: E402


def _linea_de_accion(etiqueta, op, efecto, cuesta) -> str:
    if op is None:
        return f"{etiqueta}  [SIN CONTRATO: Zeno no sabe que hace]"
    marcas = []
    if efecto == C.PUBLICA:
        marcas.append("SALE AL MUNDO")
    if cuesta:
        marcas.append("CUESTA")
    return f"{etiqueta}" + (f"  [{' · '.join(marcas)}]" if marcas else "")


def cmd_pendientes() -> int:
    lista, fallos = lector.pendientes()
    for f in fallos:
        print(f"  NO SE HA PODIDO LEER  {f}")
    if not lista:
        print("  nada espera tu OK" + (" (con lo que se ha podido leer)" if fallos else ""))
        return 0
    publican = sum(1 for p in lista if p.publica_algo)
    cuestan = sum(1 for p in lista if p.cuesta_dinero)
    huerfanas = sum(p.sin_contrato for p in lista)
    print(f"  {len(lista)} cosas esperan tu OK · {publican} pueden salir al mundo · "
          f"{cuestan} gastan API si las regeneras")
    if huerfanas:
        print(f"  OJO: {huerfanas} accion(es) sin contrato en el catalogo: Zeno no sabe que hacen")
    negocio = None
    for p in lista:
        if p.negocio != negocio:
            negocio, = (p.negocio,)
            print(f"\n  --- {negocio} ---")
        marca = "!" if p.publica_algo else " "
        print(f"  {marca} {p.titulo[:84]}")
        if p.cuerpo:
            print(f"      {p.cuerpo.splitlines()[0][:84]}")
        for a in p.acciones:
            print(f"      · {_linea_de_accion(*a)}")
    return 0


def _numero(d, *claves):
    """Primer valor numerico que exista entre esas claves. Las tres fuentes no usan los mismos
    nombres, y adivinar uno solo dejaria el resumen en blanco sin decir por que."""
    for k in claves:
        v = (d or {}).get(k)
        if isinstance(v, (int, float)):
            return v
    return None


def cmd_estado() -> int:
    datos, fallos = lector.estado()
    for f in fallos:
        print(f"  NO SE HA PODIDO LEER  {f}")
    for etiqueta, d in datos.items():
        if not isinstance(d, dict):
            continue
        print(f"\n  --- {etiqueta} ---")
        # Se imprime lo que hay, sin inventar una forma comun que las tres fuentes no comparten.
        for k, v in list(d.items())[:12]:
            if isinstance(v, (int, float, str)) and str(v)[:1]:
                print(f"      {k}: {str(v)[:70]}")
            elif isinstance(v, list):
                print(f"      {k}: {len(v)} elementos")
            elif isinstance(v, dict):
                print(f"      {k}: {', '.join(list(v)[:6])}")
    return 0


def cmd_busca(consulta: str) -> int:
    resultados, modo, fallos = lector.documentacion(consulta)
    for f in fallos:
        print(f"  NO SE HA PODIDO LEER  {f}")
    if modo == "texto":
        print("  OJO: buscando solo por TEXTO, el servicio de significado no responde")
    elif modo == "no disponible":
        print("  el corpus no esta disponible ahora mismo")
    if not resultados:
        print(f"  nada en la documentacion sobre {consulta!r}"
              f"{' (y la busqueda estaba degradada)' if modo != 'significado' else ''}")
        return 0
    print(f"  {len(resultados)} documento(s) sobre {consulta!r} · busqueda por {modo}")
    for r in resultados:
        print(f"      {(r.get('title') or r.get('doc') or '?')[:74]}")
        if r.get("sub"):
            print(f"        {r['sub'][:80]}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    orden = sys.argv[1]
    try:
        if orden == "pendientes":
            return cmd_pendientes()
        if orden == "estado":
            return cmd_estado()
        if orden == "busca":
            if len(sys.argv) < 3:
                print("  falta que buscar")
                return 2
            return cmd_busca(" ".join(sys.argv[2:]))
        if orden == "todo":
            print("  === LO QUE ESPERA TU OK ===")
            cmd_pendientes()
            print("\n  === COMO VAN LOS NEGOCIOS ===")
            cmd_estado()
            return 0
    except lector.SinClave as e:
        print(f"  {e}")
        return 3
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
