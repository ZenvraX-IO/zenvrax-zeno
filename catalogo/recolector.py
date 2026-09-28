# -*- coding: utf-8 -*-
"""Lee las acciones que las DOS colas ya declaran, y las empareja con su contrato.

POR QUE EXISTE. El asistente (plan J1) necesita una lista cerrada de lo que puede hacer. Escribirla a
mano la deja vieja en cuanto alguien añade un boton, y entonces el asistente o no ve la accion nueva
o adivina como llamarla. Asi que no se escribe: se RECOLECTA del codigo de las dos aplicaciones, y lo
que el codigo no puede decir (si es reversible, que guarda la protege) se declara en `metadatos.py`
indexado por la misma clave. Si aparece una accion sin contrato, esto FALLA: el asistente nunca ve
una accion que nadie ha declarado.

QUE SE MIDIO el 2026-09-27, leyendo el arbol de sintaxis de las dos colas:

    33 acciones · 20 EJECUTAN · 13 solo abren algo

  forma    donde     cuantas  como es
  patch    cockpit      9     {"path": ..., "verb": "POST"|"PATCH", "body": {...}}
  call     xrise        8     {"path": ..., "body": {...}}   (el verbo es POST implicito)
  url      las dos     16     una cadena; 13 abren una pagina y TRES PUBLICAN

EL HALLAZGO QUE JUSTIFICA LA FASE. Esas tres son webhooks de n8n por GET:
`linkedin-approve`, `linkedin-regenerate` y `newsletter-confirm`. Estan escritas **exactamente igual**
que un enlace a una guia en HTML. Nada en el dato distingue "abrir una vista" de "publicar en tu
nombre": lo unico que lo separa es leer la cadena y reconocer el dominio. Un asistente sobre esto
ejecutaria una publicacion creyendo que abre una pantalla, y al reves, ofreceria confirmacion para
abrir una pagina. Por eso el contrato declara `efecto` a mano y este recolector se niega a inventarlo.

NO TOCA NINGUNA DE LAS DOS APLICACIONES. Lee sus ficheros y ya. Era la alternativa a meter un campo
nuevo en las dos colas, que son la operativa diaria del operador.
"""
from __future__ import annotations

import ast
import pathlib

#: Donde vive la cola de cada sistema. Rutas relativas a la raiz de cada repo.
COLAS = {
    "cockpit": "cockpit/api/app/routers/notifications.py",
    "xrise": "saas/api/app/routers/dashboard.py",
}
_AQUI = pathlib.Path(__file__).resolve()


def _raiz_del_repo() -> pathlib.Path:
    """La raiz de zenvrax-io. Se busca hacia arriba y no se cuenta con `parents[N]`: dentro de un
    worktree (`.worktrees/<rama>/`) la profundidad es distinta que en el checkout principal, y
    contando niveles el hermano `zenvrax-xrise` se buscaba dos carpetas por debajo de donde esta."""
    for padre in _AQUI.parents:
        if (padre / "cockpit" / "api").is_dir():
            return padre
    # No se encontro. Se devuelve el propio directorio y NO `parents[3]`: dentro del contenedor el
    # codigo vive en /app/catalogo, que solo tiene dos padres, y pedir el tercero lanzaba IndexError
    # AL IMPORTAR, o sea el servicio entero no arrancaba y el contenedor reiniciaba en bucle.
    # Un repo que no esta se responde con "no esta" (lo dice `sistemas_ausentes`), no con una
    # excepcion. Se vio desplegando, no en local, donde siempre hay profundidad de sobra.
    return _AQUI.parent


def _repo_hermano(nombre: str) -> pathlib.Path:
    """Un repo hermano (`zenvrax-xrise`). En un worktree hay que subir por encima de `.worktrees`."""
    for padre in _AQUI.parents:
        candidato = padre / nombre
        if candidato.is_dir():
            return candidato
    # Mismo motivo: si no esta, se devuelve una ruta que no existe y `sistemas_ausentes` lo dira.
    return _raiz_del_repo() / nombre


#: Repos en el disco. El del cockpit es este mismo; Xrise es un repo aparte.
RAICES = {
    "cockpit": _raiz_del_repo(),
    "xrise": _repo_hermano("zenvrax-xrise"),
}


def _literal(nodo):
    """El valor de un nodo, con los huecos de una f-string marcados por su variable.

    Un `f"/content/claire/{pid}/action"` sale como `/content/claire/{pid}/action`: asi el path es
    estable entre ejecuciones y sirve de clave. Se conserva el NOMBRE de la variable en vez de un
    `{}` generico porque `{pid}` y `{cid}` distinguen dos acciones parecidas.
    """
    if isinstance(nodo, ast.Constant):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        fuera = []
        for parte in nodo.values:
            if isinstance(parte, ast.Constant):
                fuera.append(str(parte.value))
            elif isinstance(parte, ast.FormattedValue):
                v = parte.value
                nombre = (v.id if isinstance(v, ast.Name)
                          else v.attr if isinstance(v, ast.Attribute)
                          else _clave_de_indice(v))
                fuera.append("{%s}" % nombre)
        return "".join(fuera)
    if isinstance(nodo, ast.Dict):
        return {k.value: _literal(v) for k, v in zip(nodo.keys, nodo.values)
                if isinstance(k, ast.Constant)}
    if isinstance(nodo, ast.List):
        return [_literal(e) for e in nodo.elts]
    return "<dinamico>"


def _clave_de_indice(nodo) -> str:
    """`r['id']` -> `id`. Las colas indexan filas de la base todo el rato."""
    if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant):
        return str(nodo.slice.value)
    return "expr"


def acciones_declaradas(fichero: pathlib.Path) -> list[dict]:
    """Toda accion declarada en el fichero, con su linea.

    DOS FORMAS, y la segunda se añadio el 2026-09-28. Hasta entonces solo se miraban las listas
    literales bajo `"actions": [...]`, y ese dia el cockpit saco las suyas a funciones
    `acciones_magnet(pid)` para que las usaran el feed diario y la cola entera sin duplicarlas. El
    recolector dejo de verlas y DIEZ contratos se quedaron sin boton de golpe: los botones
    seguian ahi, pero sin contrato el ejecutor los rechaza, o sea Zeno se quedaba sin poder
    aprobar nada. Lo dijeron cuatro tests a la vez, no el servidor.
    """
    arbol = ast.parse(fichero.read_text(encoding="utf-8", errors="replace"))
    fuera = []

    def _mete(lista):
        for elemento in lista.elts:
            if isinstance(elemento, ast.Dict):
                d = _literal(elemento)
                if isinstance(d, dict) and d:
                    d["_linea"] = elemento.lineno
                    fuera.append(d)

    for nodo in ast.walk(arbol):
        # Forma 1: escritas dentro de la notificacion.
        if isinstance(nodo, ast.Dict):
            for clave, valor in zip(nodo.keys, nodo.values):
                if (isinstance(clave, ast.Constant) and clave.value == "actions"
                        and isinstance(valor, ast.List)):
                    _mete(valor)
        # Forma 2: una funcion `acciones_*` que las devuelve, para que no haya dos copias.
        if (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                and nodo.name.startswith("acciones_")):
            for hijo in ast.walk(nodo):
                if isinstance(hijo, ast.Return) and isinstance(hijo.value, ast.List):
                    _mete(hijo.value)
    return fuera


def _normaliza(accion: dict, sistema: str) -> dict:
    """Las tres formas a una sola. `patch` y `call` son la misma cosa con otro nombre."""
    ejecuta = accion.get("patch") or accion.get("call")
    forma = "patch" if "patch" in accion else ("call" if "call" in accion else "url")
    if ejecuta and isinstance(ejecuta, dict):
        destino = ejecuta.get("path")
        # El verbo por omision NO es el mismo en las dos colas, y se ha leido de quien las ejecuta:
        #   cockpit  Notificaciones.tsx:228   api(a.patch.path, a.patch.verb || "PATCH", ...)
        #   xrise    Notificaciones.tsx:119   api(a.call.path, "POST", ...)      <- fijo, sin verbo
        # Suponer POST para las dos costo un falso negativo: `tema.marcar_publicado` no declara verbo
        # y se dio por un POST que no existe, cuando el endpoint real es PATCH /marketing/topics/{id}.
        verbo = ejecuta.get("verb") or ("PATCH" if forma == "patch" else "POST")
        cuerpo = ejecuta.get("body") or {}
    else:
        destino = accion.get("url")
        verbo = "GET"
        cuerpo = {}
    return {
        "sistema": sistema,
        "forma": forma,
        "etiqueta": accion.get("label"),
        "destino": destino,
        "verbo": verbo,
        "cuerpo": cuerpo,
        "linea": accion.get("_linea"),
    }


def clave(accion: dict) -> str:
    """Identificador estable de una accion.

    Lleva la ETIQUETA a proposito, y no solo el destino: `/marketing/magnet-promo/{id}` recibe tres
    PATCH distintos que solo se diferencian por su cuerpo, y dos enlaces del cockpit se construyen en
    una variable, asi que su destino sale como `<dinamico>` y sin la etiqueta serian el mismo.
    """
    cuerpo = ",".join(f"{k}={v}" for k, v in sorted((accion["cuerpo"] or {}).items()))
    return f"{accion['sistema']}|{accion['verbo']}|{accion['destino']}|{cuerpo}|{accion['etiqueta']}"


def recolecta(sistemas=None) -> list[dict]:
    """Las acciones de las colas que estan presentes en el disco, normalizadas.

    Si el repo de un sistema no esta (Xrise es un repo aparte y puede no estar clonado), se OMITE en
    vez de fallar, y `sistemas_ausentes()` lo dice. Un recolector que revienta porque falta un repo
    hermano no se puede usar en el arranque del asistente.
    """
    fuera = []
    for sistema, relativo in COLAS.items():
        if sistemas and sistema not in sistemas:
            continue
        fichero = RAICES[sistema] / relativo
        if not fichero.exists():
            continue
        for accion in acciones_declaradas(fichero):
            fuera.append(_normaliza(accion, sistema))
    return fuera


def sistemas_ausentes() -> list[str]:
    return [s for s, rel in COLAS.items() if not (RAICES[s] / rel).exists()]
