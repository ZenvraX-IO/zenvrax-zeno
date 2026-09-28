# -*- coding: utf-8 -*-
"""El compose no puede contradecir al codigo: si lo hace, degrada en silencio.

EL CASO, medido el 28-sep. El ejecutor tiene dos listas con un default correcto: ZENO_CASAS (a
quien se puede llamar) y ZENO_CON_CLAVE (a quien se le manda la clave de escritura). El compose
ponia las dos variables, pero la primera SIN las direcciones internas y la segunda sin poner nada.

Resultado: Zeno leia por http://cockpit-api:8802, el lector ponia esa url en la accion "Marcar
hecha", y su propio ejecutor la rechazaba con "esa direccion no es de ninguno de los sistemas de
casa". Y aunque hubiera pasado, la clave no se mandaba a nadie y el cockpit contestaba 401.

Ningun test podia verlo: los del ejecutor corren con los defaults del codigo, que estan bien. Lo
que estaba mal era la capa de al lado. De ahi que esto lea el YAML y no el modulo.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
COMPOSE = RAIZ / "infra" / "docker-compose.zeno.yml"


def _variables() -> dict[str, str]:
    """Lee las variables de entorno del compose con su default `${X:-valor}` ya resuelto.

    Se lee con una expresion y no con un parser de YAML: lo que importa es el texto que acaba en
    el contenedor, y aqui no hay anclas ni listas anidadas.
    """
    fuera = {}
    for linea in COMPOSE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(ZENO_[A-Z_]+):\s*(.+?)\s*$", linea)
        if not m:
            continue
        valor = m.group(2)
        d = re.fullmatch(r"\$\{[A-Z_]+:-(.*)\}", valor)
        if d:
            valor = d.group(1)
        elif re.fullmatch(r"\$\{[A-Z_]+\}", valor):
            valor = ""          # secreto que viene del .env: aqui no se puede saber
        fuera[m.group(1)] = valor
    return fuera


def _lista(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def test_a_donde_lee_zeno_esta_entre_las_casas():
    """EL TEST QUE FALTABA. La url de una accion se construye con estas bases; si no empiezan por
    una casa, el ejecutor rechaza su propia url."""
    v = _variables()
    casas = _lista(v["ZENO_CASAS"])
    for clave in ("ZENO_COCKPIT_URL", "ZENO_XRISE_URL"):
        base = v[clave].rstrip("/") + "/"
        assert any(base.startswith(c) for c in casas), (
            f"{clave}={v[clave]} no empieza por ninguna de ZENO_CASAS={casas}: "
            "el ejecutor rechazara toda accion que apunte ahi")


def test_la_clave_de_escritura_llega_al_cockpit():
    """Sin esto la accion sale pero el cockpit contesta 401, que es lo que paso."""
    v = _variables()
    con_clave = _lista(v.get("ZENO_CON_CLAVE", ""))
    assert con_clave, "ZENO_CON_CLAVE vacio: el ejecutor no manda la clave a nadie"
    base = v["ZENO_COCKPIT_URL"].rstrip("/") + "/"
    assert any(base.startswith(c) for c in con_clave), (
        f"a {base} no se le manda la clave: ZENO_CON_CLAVE={con_clave}")


def test_la_clave_no_se_manda_a_n8n():
    """Una credencial va a quien tiene que recibirla, no a todo el que aparezca en una url. n8n es
    de casa y no la necesita."""
    v = _variables()
    for destino in _lista(v.get("ZENO_CON_CLAVE", "")):
        assert "n8n" not in destino, f"la clave de escritura viaja a n8n: {destino}"


def test_el_compose_no_pisa_los_defaults_del_codigo_con_menos():
    """La trampa concreta: el codigo tenia la lista buena y el compose la recortaba. Si una de las
    dos listas se escribe en los dos sitios, el compose no puede tener MENOS entradas."""
    import os
    import sys
    sys.path.insert(0, str(RAIZ))
    v = _variables()
    # Se importa con el entorno limpio para leer los defaults del modulo, no lo que haya puesto.
    guardado = {k: os.environ.pop(k, None) for k in ("ZENO_CASAS", "ZENO_CON_CLAVE")}
    try:
        for m in [x for x in list(sys.modules) if x.endswith("ejecutor")]:
            del sys.modules[m]
        from servicio import ejecutor
        for nombre, del_codigo in (("ZENO_CASAS", ejecutor.CASAS),
                                   ("ZENO_CON_CLAVE", ejecutor.CON_CLAVE)):
            faltan = set(del_codigo) - set(_lista(v.get(nombre, "")))
            assert not faltan, f"{nombre} del compose pierde lo que el codigo si tenia: {sorted(faltan)}"
    finally:
        for k, val in guardado.items():
            if val is not None:
                os.environ[k] = val
