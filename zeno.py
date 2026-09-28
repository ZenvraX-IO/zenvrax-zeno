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
    lista, _avisos, fallos = lector.pendientes()
    for f in fallos:
        print(f"  NO SE HA PODIDO LEER  {f}")
    if not lista:
        print("  nada espera tu OK" + (" (con lo que se ha podido leer)" if fallos else ""))
        return 0
    publican = sum(1 for p in lista if p.publica_algo)
    cuestan = sum(1 for p in lista if p.cuesta_dinero)
    huerfanas = sum(p.sin_contrato for p in lista)
    # Sin comillas anidadas dentro de la f-string: eso solo compila en Python 3.12 y este guion
    # tambien se ejecuta en el servidor, donde la version puede ser otra.
    cuantas = f"{len(lista)} cosas esperan" if len(lista) != 1 else "1 cosa espera"
    print(f"  {cuantas} tu OK · {publican} pueden salir al mundo · "
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


def _kpis(negocio: dict) -> list[str]:
    """Los KPIs de un negocio, con la alerta que ya trae el dato. `alerta` puede ser bad o warn, y lo
    pone el cockpit: Zeno no decide que es preocupante, lo repite."""
    fuera = []
    for k in negocio.get("kpis") or []:
        marca = {"bad": "  <-- MAL", "warn": "  <-- ojo"}.get(k.get("alerta"), "")
        fuera.append(f"{k.get('k')}: {k.get('v')}{marca}")
    return fuera


def cmd_estado() -> int:
    datos, fallos = lector.estado()
    for f in fallos:
        print(f"  NO SE HA PODIDO LEER  {f}")

    # --- los dos negocios, del overview de AIOS ---
    for negocio in (datos.get("zenvrax") or {}).get("negocios") or []:
        print(f"\n  --- {negocio.get('nombre')} ({negocio.get('sub')}) ---")
        lineas = _kpis(negocio)
        if lineas:
            for l in lineas:
                print(f"      {l}")
        elif negocio.get("nota"):
            # Un negocio sin KPIs no es un negocio parado: el dato aun no esta conectado, y el
            # propio cockpit lo explica. Repetir la nota es mas honesto que imprimir una lista vacia.
            print(f"      {negocio['nota']}")
        salud = negocio.get("salud") or {}
        if salud:
            print(f"      workflows: {salud.get('activos')} activos de {salud.get('total')}"
                  f" · con error: {salud.get('errores')}")

    # --- lo que Xrise cuenta de GutLyn y el cockpit no sabe ---
    alertas = (datos.get("gutlyn") or {}).get("alerts") or []
    encendidas = [a for a in alertas if a.get("value") and a.get("tone") != "ok"]
    if alertas:
        print(f"\n  --- GutLyn, del panel de Xrise · "
              f"{len(encendidas)} de {len(alertas)} encendidas ---")
        for a in encendidas:
            print(f"      {a.get('label')}: {a.get('value')}")
        if not encendidas:
            print("      nada encendido")

    # --- el plan del dia ---
    plan = datos.get("plan_del_dia") or {}
    foco = plan.get("focus") or {}
    cuentas = plan.get("counts") or {}
    if foco or cuentas:
        print("\n  --- el plan de hoy ---")
        if foco:
            print(f"      lo primero: {(foco.get('title') or '')[:74]}")
            if foco.get("body"):
                print(f"                  {foco['body'][:74]}")
        if cuentas:
            print(f"      {cuentas.get('pending', 0)} pendientes · "
                  f"{cuentas.get('urgent', 0)} urgentes · "
                  f"{cuentas.get('done_today', 0)} hechas hoy")
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
