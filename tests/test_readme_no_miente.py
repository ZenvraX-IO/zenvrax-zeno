# -*- coding: utf-8 -*-
"""El README dice cifras y rutas. Que sigan siendo verdad.

EL CASO (2026-09-28). Al preguntar el operador "que falta de Zeno", el primer sitio donde mire fue
el README, y decia tres cosas falsas: que faltaba Xrise y que las 31 de GutLyn no se abrian (se
abren), que Zeno vivia en `lab/` (graduo ese mismo dia) y que el catalogo tenia 33 acciones (tiene
40). Ninguna prueba se enteraba, porque un documento no se ejecuta.

Es el primer fichero que lee cualquiera que llegue al repo, yo incluido en la siguiente sesion, y
un mapa falso hace tomar decisiones falsas: ya paso con el CLAUDE.md del cockpit, que afirmo trece
semanas seis agentes Python que nunca existieron.

Esto NO revisa la prosa, solo lo comprobable: las cifras contra el catalogo y que los comandos no
apunten a una ruta que ya no existe.
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

README = (RAIZ / "README.md").read_text(encoding="utf-8")
CATALOGO = json.loads((RAIZ / "catalogo" / "congelado.json").read_text(encoding="utf-8"))
ACCIONES = [a for a in (CATALOGO["acciones"] if isinstance(CATALOGO, dict) and "acciones" in CATALOGO
                        else CATALOGO) if isinstance(a, dict)]


def test_el_numero_de_acciones_del_readme_es_el_del_catalogo():
    """Decia 33 con 40 en el fichero. Quien lea 33 se cree que la lista es mas corta de lo que es,
    y esa lista es la superficie por la que Zeno puede tocar los dos negocios."""
    dice = re.search(r"\*\*(\d+) acciones\*\*", README)
    assert dice, "el README ya no dice cuantas acciones hay"
    assert int(dice.group(1)) == len(ACCIONES), (
        f"el README dice {dice.group(1)} acciones y el catalogo tiene {len(ACCIONES)}")


def test_el_reparto_por_sistema_cuadra():
    cockpit = sum(1 for a in ACCIONES if a.get("sistema") == "cockpit")
    xrise = sum(1 for a in ACCIONES if a.get("sistema") == "xrise")
    assert f"{cockpit} del cockpit, {xrise} de Xrise" in README, (
        f"el reparto real es {cockpit} del cockpit y {xrise} de Xrise")


def test_las_que_escriben_cuadran():
    """La cifra que de verdad importa: cuantas de las 40 cambian algo. Las demas solo abren una
    pantalla y no pueden estropear nada."""
    escriben = sum(1 for a in ACCIONES if a.get("efecto") != "abre")
    assert f"**{escriben} escriben algo**" in README, f"escriben {escriben}, no lo que dice el README"


def test_ningun_comando_apunta_a_la_carpeta_de_antes_de_graduar():
    """`python -m pytest lab/zeno/tests` no existe desde el 28-sep: quien lo copie recibe un error
    y no sabra si es el repo o es el. Los comandos de un README se copian, no se leen."""
    for linea in README.splitlines():
        if linea.strip().startswith(("python", "cd ", "docker", "ZENO_")):
            assert "lab/zeno" not in linea, f"comando con la ruta vieja: {linea.strip()}"


def test_el_despliegue_apunta_al_repo_graduado_y_lleva_sus_dos_banderas():
    """Sin `-p zeno` Docker crea un volumen vacio y se pierden las passkeys, el permiso de Google,
    el diario y la memoria. Sin `--env-file` el contenedor arranca sin secretos. Las dos han
    tumbado ya un servicio de esta casa."""
    i = README.index("## Desplegar")
    bloque = README[i:i + 700]
    assert "/home/zenvrax-zeno" in bloque, "el despliegue sigue apuntando a donde vivia antes"
    assert "-p zeno" in bloque and "--env-file" in bloque
    # Y que NINGUNA linea entre a por el repo del cockpit. La primera version solo miraba que la
    # ruta nueva apareciera, y aparece dos veces: el `cd` podia seguir yendo a zenvrax-io y el
    # guardian pasaba. Lo encontro la prueba en rojo, no la lectura.
    assert "/home/zenvrax-io && git pull" not in bloque, (
        "el despliegue hace git pull en el repo del cockpit, no en el de Zeno")


def test_no_se_anuncia_como_pendiente_algo_que_ya_esta_hecho():
    """J3 y J4 estuvieron cerradas y seguian escritas como lo siguiente. Un pendiente falso hace
    que se vuelva a plantear un trabajo ya hecho, que es tiempo tirado."""
    for fantasma in ("Falta Xrise", "Vive en `lab/`", "**J3:", "**J4:"):
        assert fantasma not in README, f"el README anuncia como pendiente algo hecho: {fantasma}"
