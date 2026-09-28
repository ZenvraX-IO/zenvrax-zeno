# -*- coding: utf-8 -*-
"""Entender una orden dicha en voz alta y emparejarla con una accion que ya existe.

POR QUE NO LO DECIDE EL MODELO. Seria una linea de prompt, y seria la pieza mas peligrosa del
sistema: un modelo que elige que accion disparar puede elegir mal, y aqui elegir mal significa
tocar el trabajo de verdad. Esto empareja con reglas, es determinista, se prueba entero sin red y
sin gastar un centimo, y no puede inventarse una accion que no estuviera ya en la pantalla.

LA BARRERA, decidida por el operador el 28-sep: por voz solo lo que se deshace. Lo que sale al
mundo (aprobar y publicar, enviar la newsletter, lanzar una campaña) sigue pidiendo el dedo y el
PIN. Una frase mal entendida no puede publicar en su nombre, y un PIN dicho en alto se oye.

Y una regla que parece menor y no lo es: si la frase encaja con DOS cosas, no se hace ninguna.
Preguntar cual de las dos cuesta tres segundos; acertar la que no era cuesta deshacerlo.
"""
from __future__ import annotations

import re
import unicodedata

#: Lo que se puede pedir hablando, y con que etiquetas del catalogo casa cada cosa. Las claves son
#: como lo dice una persona; los valores, trozos de la etiqueta real que puso quien escribio el
#: sistema. Se comparan sin acentos y en minuscula.
VERBOS: dict[str, tuple[str, ...]] = {
    "marcar hecha": ("marcar hecha", "marcar publicado", "ya esta programado", "hecha", "hecho"),
    "descartar": ("descartar", "cancelar", "no postear", "saltar"),
    "posponer": ("posponer", "no postear"),
}

#: Como empieza una frase que es una ORDEN y no una pregunta. Sin esto, "marco la tarea como
#: hecha?" se ejecutaria como si fuera una orden.
ARRANQUES = ("marca", "marcame", "cierra", "cierrame", "descarta", "descartame", "cancela",
             "pospon", "posponla", "posponlo", "aplaza", "salta", "saltate", "da por hecha",
             "dala por hecha", "dalo por hecho", "ponla como hecha", "ponlo como hecho")

#: Con que empieza una PREGUNTA. El dictado casi nunca pone signos, asi que no se puede depender
#: del interrogante para distinguir "cierra la tarea" de "cierro la tarea o no".
PREGUNTAS = ("que", "cuanto", "cuantos", "cuanta", "cuando", "cual", "cuales", "quien", "como",
             "donde", "dime", "cuentame", "hay", "tengo", "puedo", "sabes", "deberia")

#: Palabras que no distinguen nada al buscar de que cosa habla. Sin quitarlas, "la tarea de la
#: landing" casa con cualquier aviso que lleve "la" o "de".
VACIAS = {"el", "la", "los", "las", "un", "una", "de", "del", "al", "a", "en", "y", "o", "que",
          "como", "por", "para", "con", "lo", "le", "se", "su", "sus", "esta", "este", "esa",
          "ese", "tarea", "aviso", "cosa", "hecha", "hecho", "marca", "cierra", "descarta",
          "cancela", "pospon", "ya", "mi", "me", "yo", "post"}


def limpia(t: str) -> str:
    """Minusculas, sin acentos y sin signos. Lo que se dicta no viene con tildes fiables."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def es_orden(frase: str) -> bool:
    """Si la frase manda hacer algo. Una pregunta NO es una orden, aunque hable de lo mismo."""
    f = limpia(frase)
    if not f or "?" in (frase or ""):
        return False
    if f.split()[0] in PREGUNTAS:
        return False
    return any(f.startswith(a) for a in ARRANQUES)


def _que_verbo(frase: str) -> str | None:
    f = limpia(frase)
    if f.startswith(("descarta", "cancela", "salta")):
        return "descartar"
    if f.startswith(("pospon", "aplaza")):
        return "posponer"
    if f.startswith(("marca", "cierra", "da por", "dala", "dalo", "ponla", "ponlo")):
        return "marcar hecha"
    return None


def _palabras(t: str) -> set[str]:
    return {p for p in limpia(t).split() if p not in VACIAS and len(p) > 2}


def se_puede_por_voz(accion: dict) -> bool:
    """LA BARRERA. Por voz solo lo reversible, barato y que no sale al mundo.

    Las tres condiciones, no una: `reversible` lo dice el catalogo, `publica` es lo que no se
    recoge, y `coste_api` es dinero que se gasta sin que nadie haya visto la cifra. "Regenerar" es
    justo el caso que las tres juntas paran: cambia un estado, pero no se deshace y cuesta.
    """
    return (bool(accion.get("reversible"))
            and accion.get("efecto") == "cambia_estado"
            and not accion.get("coste_api"))


def por_que_no(accion: dict) -> str:
    """En castellano, por que esa accion no se hace hablando. Sirve para decirlo en voz alta."""
    if accion.get("efecto") == "publica":
        return "eso sale al mundo y no se deshace, hazlo con el botón"
    if accion.get("coste_api"):
        return "eso cuesta dinero, hazlo con el botón"
    return "eso no se puede deshacer, hazlo con el botón"


def empareja(frase: str, cosas: list[dict]) -> dict:
    """Busca a que cosa de la pantalla se refiere la frase, y con que accion.

    `cosas` son los pendientes y avisos tal como salen de la API, cada uno con `titulo` y
    `acciones`. Devuelve {"estado": ...} y, si sale bien, la cosa y la accion.

    Estados posibles, y los cinco que NO son "vale" importan tanto como el que si:
      · `no_es_orden`   la frase no manda nada: es una pregunta, va al chat.
      · `no_entiendo`   manda algo, pero no se sabe el que.
      · `nada_encaja`   no hay ninguna cosa en pantalla que se parezca.
      · `varias`        encaja con mas de una: se pregunta, no se adivina.
      · `no_por_voz`    la accion existe pero no se hace hablando.
      · `vale`          todo claro.
    """
    if not es_orden(frase):
        return {"estado": "no_es_orden"}
    verbo = _que_verbo(frase)
    if not verbo:
        return {"estado": "no_entiendo"}

    dichas = _palabras(frase)
    candidatas = []
    for c in cosas or []:
        acc = None
        for a in c.get("acciones") or []:
            et = limpia(a.get("etiqueta") or "")
            if any(pista in et for pista in VERBOS[verbo]):
                acc = a
                break
        if not acc:
            continue
        comunes = dichas & _palabras(c.get("titulo") or "")
        if comunes:
            candidatas.append((len(comunes), c, acc))

    if not candidatas:
        return {"estado": "nada_encaja", "verbo": verbo}
    candidatas.sort(key=lambda x: -x[0])
    # Empate: dos cosas encajan igual de bien. No se elige la primera; se pregunta. Acertar la que
    # no era cuesta deshacerlo, y deshacerlo desde el movil es justo lo que se venia a evitar.
    if len(candidatas) > 1 and candidatas[0][0] == candidatas[1][0]:
        return {"estado": "varias", "verbo": verbo,
                "cuales": [c.get("titulo") for _, c, _ in candidatas[:3]]}

    _, cosa, accion = candidatas[0]
    if not se_puede_por_voz(accion):
        return {"estado": "no_por_voz", "cosa": cosa, "accion": accion,
                "por_que": por_que_no(accion)}
    return {"estado": "vale", "cosa": cosa, "accion": accion, "verbo": verbo}


#: Lo que cuenta como un si y como un no al confirmar en voz. Nada que no este aqui se toma como
#: un no: ante la duda, no se ejecuta. Es la unica asimetria a proposito del modulo.
SIES = ("si", "sí", "vale", "claro", "hazlo", "adelante", "correcto", "eso es", "dale", "venga",
        "confirmo", "exacto", "afirmativo", "ok", "okey")
NOES = ("no", "para", "espera", "deja", "dejalo", "cancela", "anula", "mejor no", "negativo")


def dice_que_si(frase: str) -> bool:
    """Si la respuesta a la confirmacion es un si CLARO. Todo lo demas es un no.

    Se compara la frase entera y su primera palabra, no "contiene": "no, mejor no lo hagas" lleva
    dentro la palabra "hagas" y un `in` mal puesto lo leeria como un si.
    """
    f = limpia(frase)
    if not f:
        return False
    if f.split()[0] in ("no", "para", "espera", "deja", "dejalo", "cancela", "anula", "negativo"):
        return False
    return f in [limpia(s) for s in SIES] or f.split()[0] in [limpia(s).split()[0] for s in SIES]
