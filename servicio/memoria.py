# -*- coding: utf-8 -*-
"""Lo que Zeno recuerda de un dia para otro.

EL CASO (2026-09-28). Zeno hacia de todo menos acordarse: el chat llevaba seis turnos leidos de
la pantalla y al cerrar la aplicacion no sabia quien eres, que decidiste ayer ni que te molesta.
Un asistente que cada manana empieza de cero es una herramienta.

TRES COSAS SE GUARDAN, y son distintas a proposito:

  · `dicho`   lo que el operador pidio recordar, con sus palabras.
  · `hecho`   lo que Zeno hizo, que ya vivia en el diario y nadie estaba usando.
  · `hilo`    la conversacion, para poder seguirla manana.

POR QUE NO LO DECIDE EL MODELO. La tentacion es pedirle que "recuerde lo importante" de cada
conversacion. Eso guarda cosas que nadie dijo y las repite despues como ciertas, que es
exactamente lo contrario de la regla del operador sobre hechos comprobados. Aqui solo se apunta
lo que EL pidio apuntar o lo que de verdad paso, y cada apunte lleva de donde salio.

Y TODO SE PUEDE BORRAR. Una memoria que no se puede mirar ni corregir acaba mintiendo con
autoridad: el operador leeria un apunte viejo como si fuera cierto hoy.
"""
from __future__ import annotations

import json
import os
import time
import uuid
import unicodedata
from pathlib import Path

#: Append-only, como el diario, y por el mismo motivo: un fichero que solo crece no se corrompe a
#: medias, y su ultima linea rota se descarta sin perder lo anterior.
FICHERO = Path(os.environ.get("ZENO_MEMORIA", "/datos/memoria.jsonl"))

#: Cuantos apuntes viajan con cada pregunta. Veinte frases cortas son unas 300 palabras: al coste
#: medido (0,0017 USD por pregunta) eso no se nota, y mas empieza a tapar lo que si importa.
CUANTOS = int(os.environ.get("ZENO_MEMORIA_CUANTOS", "20"))

#: Cuantos turnos de la conversacion de AYER se recuperan. Pocos: es para retomar el hilo, no
#: para revivir la conversacion entera.
TURNOS_GUARDADOS = int(os.environ.get("ZENO_HILO", "8"))

#: Como se le pide a Zeno que apunte algo. Se reconoce con reglas y no con el modelo, igual que
#: las ordenes de voz: lo que se guarda tiene que ser exactamente lo que se dijo.
ARRANQUES = ("recuerda que", "recuerda ", "apunta que", "apunta ", "no olvides que",
             "no olvides ", "ten en cuenta que", "ten en cuenta ", "acuerdate de que",
             "acuerdate de ", "memoriza que", "memoriza ")


def _limpia(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def es_para_recordar(frase: str) -> str:
    """Si la frase pide apuntar algo, devuelve QUE apuntar. Si no, cadena vacia.

    Devuelve el texto tal cual lo dijo el operador, sin el arranque: guardar "recuerda que los
    martes no publico" dejaria la orden dentro del recuerdo y se leeria raro al recuperarlo.
    """
    f = _limpia(frase)
    for a in ARRANQUES:
        if f.startswith(_limpia(a)):
            resto = (frase or "").strip()[len(a):].strip()
            # Se comprueba sobre el ORIGINAL para no perder tildes ni mayusculas.
            if not resto:
                return ""
            return resto[0].upper() + resto[1:] if len(resto) > 1 else resto
    return ""


def _lee_lineas() -> list[dict]:
    try:
        crudo = FICHERO.read_text(encoding="utf-8")
    except OSError:
        return []
    fuera = []
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            fuera.append(json.loads(linea))
        except ValueError:
            continue          # una linea rota (un corte a medias) no se lleva las demas
    return fuera


def _escribe(apunte: dict) -> None:
    """Anade una linea. NUNCA lanza: que la memoria falle no puede tumbar lo que se estaba
    haciendo, igual que en el diario."""
    try:
        FICHERO.parent.mkdir(parents=True, exist_ok=True)
        # Si la ultima linea quedo a medias por un corte, se cierra antes de anadir.
        if FICHERO.exists():
            crudo = FICHERO.read_text(encoding="utf-8")
            if crudo and not crudo.endswith("\n"):
                with FICHERO.open("a", encoding="utf-8") as f:
                    f.write("\n")
        with FICHERO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(apunte, ensure_ascii=False) + "\n")
    except OSError:
        pass


def apunta(texto: str, origen: str = "dicho") -> dict:
    """Guarda un apunte. `origen` dice de donde salio, y eso viaja con el para siempre."""
    texto = (texto or "").strip()
    if not texto:
        return {}
    # EL ID LLEVA AZAR, y no es cosmetico. La primera version era solo la hora en milisegundos: dos
    # apuntes seguidos (el chat guarda pregunta y respuesta de golpe) salian con el MISMO id, y
    # olvidar uno borraba los dos. Lo cazo un test; en produccion habria sido el operador viendo
    # desaparecer un apunte que no habia tocado.
    apunte = {"id": f"{int(time.time() * 1000):x}{uuid.uuid4().hex[:6]}", "texto": texto[:400],
              "origen": origen, "cuando": time.time()}
    _escribe(apunte)
    return apunte


def olvida(ident: str) -> bool:
    """Marca un apunte como olvidado. NO se borra la linea: se anade una que lo tacha.

    Append-only tambien aqui. Reescribir el fichero para quitar una linea es la operacion que
    puede dejarlo a medias y llevarse lo demas, y esto guarda decisiones del operador.
    """
    if not ident:
        return False
    _escribe({"olvida": ident, "cuando": time.time()})
    return True


def apuntes(limite: int = 0) -> list[dict]:
    """Los apuntes vivos, del mas nuevo al mas viejo."""
    lineas = _lee_lineas()
    olvidados = {x["olvida"] for x in lineas if x.get("olvida")}
    vivos = [x for x in lineas if x.get("id") and x["id"] not in olvidados]
    vivos.sort(key=lambda x: x.get("cuando", 0), reverse=True)
    return vivos[:limite] if limite else vivos


def para_el_contexto(cuantos: int = 0) -> str:
    """Los apuntes en texto, para meterlos en el prompt. Vacio si no hay nada.

    Lo dicho por el operador va PRIMERO y con su marca: entre "lo dijo el" y "lo dedujo de una
    accion" hay una diferencia que el modelo tiene que ver, porque lo segundo se equivoca.
    """
    xs = apuntes(cuantos or CUANTOS)
    if not xs:
        return ""
    dichos = [x for x in xs if x.get("origen") == "dicho"]
    otros = [x for x in xs if x.get("origen") != "dicho"]
    trozos = []
    if dichos:
        trozos.append("LO QUE EL OPERADOR TE HA PEDIDO RECORDAR:\n"
                      + "\n".join("  - " + x["texto"] for x in dichos))
    if otros:
        trozos.append("DE LO QUE HA PASADO:\n"
                      + "\n".join("  - " + x["texto"] for x in otros))
    return "\n\n".join(trozos)


# ---------------------------------------------------------------- el hilo de la conversacion

HILO = Path(os.environ.get("ZENO_HILO_FICHERO", "/datos/conversacion.jsonl"))

#: Cuantos turnos se conservan en disco. Solo se leen los ultimos ocho: el resto esta para poder
#: mirar atras desde la pantalla, no para el modelo. Pasado esto se recorta, porque un fichero de
#: conversacion que crece sin fin acaba tardando en leerse en cada pregunta.
TOPE_HILO = 300


def guarda_turno(de: str, texto: str) -> None:
    """Un turno de la conversacion. Se guarda para poder retomarla manana.

    NO es lo mismo que un apunte: esto caduca y se sustituye, un apunte se queda hasta que el
    operador lo borre.
    """
    texto = (texto or "").strip()
    if not texto:
        return
    try:
        HILO.parent.mkdir(parents=True, exist_ok=True)
        with HILO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"de": de, "texto": texto[:2000], "cuando": time.time()},
                               ensure_ascii=False) + "\n")
        lineas = HILO.read_text(encoding="utf-8").splitlines()
        if len(lineas) > TOPE_HILO:
            HILO.write_text("\n".join(lineas[-TOPE_HILO:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def hilo(cuantos: int = 0) -> list[dict]:
    """Los ultimos turnos, del mas viejo al mas nuevo (que es como los espera el modelo)."""
    try:
        crudo = HILO.read_text(encoding="utf-8")
    except OSError:
        return []
    fuera = []
    for linea in crudo.splitlines():
        try:
            fuera.append(json.loads(linea))
        except ValueError:
            continue
    return fuera[-(cuantos or TURNOS_GUARDADOS):]


def cuando_fue_lo_ultimo() -> float:
    """Cuando se hablo por ultima vez. Sirve para saber si hay que retomar algo o empezar."""
    xs = hilo(1)
    return float(xs[0].get("cuando", 0)) if xs else 0.0


def olvida_el_hilo() -> None:
    """Corta la conversacion. Lo pide el operador cuando quiere empezar de cero."""
    try:
        HILO.write_text("", encoding="utf-8")
    except OSError:
        pass
