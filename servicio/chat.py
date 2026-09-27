# -*- coding: utf-8 -*-
"""El chat de Zeno. Con Haiku, con tope diario y contando cada céntimo.

EL MODELO ES HAIKU, y no por ahorrar sin más. El operador: *"tampoco creo que deba tener ese coste
puesto el modelo debería ser haiku"*. Medido sobre 30 días reales del ecosistema:

    claude-haiku-4-5      10.251 llamadas   $0,0017 de media
    claude-sonnet-4-6        716 llamadas   $0,0079 de media

O sea Haiku es **4,5 veces más barato**, y esto no es razonamiento complejo: es contestar sobre un
contexto que Zeno ya tiene delante. La regla de la casa lo dice desde agosto, y encaja: la voz y el
criterio los pone el PROMPT, no el modelo.

EL CONTEXTO VA PRECARGADO, no se le dan herramientas. Zeno ya sabe lo que hay pendiente, cuánto
queda en cada cola y qué dice el corpus: se le pasa todo eso en el mensaje y contesta. Darle
herramientas multiplicaría las llamadas por pregunta, que es justo lo que encarece un chat.

EL TOPE DIARIO NO ES DECORATIVO. Un chat es la única pieza de Zeno cuyo coste lo decide el uso, no
el sistema. Sin tope, una tarde de curiosidad se convierte en una factura que nadie vio venir, que
es exactamente lo que ya pasó en este ecosistema en agosto.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date

MODELO = os.environ.get("ZENO_MODELO", "claude-haiku-4-5")
CLAVE_ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY", "")
#: Tope de preguntas al día. A $0,0017 la pregunta, 60 son unos 10 céntimos: suficiente para un día
#: de uso intenso y un techo que no asusta. Se cuenta en memoria: si el contenedor se reinicia se
#: pone a cero, y eso es aceptable para un tope que protege de un despiste, no de un ataque.
TOPE_DIARIO = int(os.environ.get("ZENO_TOPE_PREGUNTAS", "60"))

#: Precio por millón de tokens de Haiku 4.5, para poder decir lo que cuesta cada respuesta.
PRECIO_ENTRADA, PRECIO_SALIDA = 1.00, 5.00

_gastado: dict[str, int] = {}


class SinClaveDeIA(RuntimeError):
    """No hay clave de Anthropic. Se dice en vez de contestar vacío."""


class TopeAlcanzado(RuntimeError):
    """Se han hecho las preguntas del día. Dice cuántas van y cuál es el tope."""


SISTEMA = """Eres Zeno, el asistente del operador de Zenvrax IO.

Contestas sobre DOS negocios que están separados y no se mezclan:
  - Zenvrax IO: la consultoría de automatización.
  - GutLyn+ (marca HAAZON): el ecommerce, que se gestiona desde Xrise.

REGLAS, y son duras:
  - Responde SOLO con los datos del contexto. Si algo no está, di que no lo sabes y dónde mirarlo.
    Inventar una cifra de negocio es peor que no contestar.
  - UN CERO NO ES UNA AUSENCIA. Si el contexto dice que los ingresos son 0 o que no hay pedidos,
    esa ES la respuesta: dila con su cifra y explica por qué, no digas que no tienes el dato.
  - Si el contexto avisa de que una fuente no respondió, DILO antes de dar números: una lista corta
    sin aviso se lee como "hay poco".
  - Lo que publica hacia fuera (LinkedIn, X, Meta, correo) es irreversible. Nómbralo como tal.
  - Nunca propongas ejecutar una acción tú mismo: todavía no puedes. Di dónde está el botón.
  - En español, directo, sin rodeos ni disculpas. Frases cortas. Sin asteriscos y sin raya larga.
"""


def _limpia(texto: str) -> str:
    """Quita los asteriscos y la raya larga de la respuesta.

    El operador tiene dos reglas duras sobre esto y el prompt NO las garantiza: en la primera prueba
    real el modelo contesto con `**Hoy tienes pendiente:**` teniendo la prohibicion escrita. Un
    prompt es una peticion; esto es la garantia. Cinturon y tirantes, porque la regla es del
    operador y no de una preferencia mia.
    """
    # Se quita el asterisco a secas, SIN expresion regular de captura. La primera version usaba
    # una re.sub con grupo y referencia ; al pasar por el shell la referencia se perdio y la
    # expresion BORRABA el texto en vez de conservarlo. Se vio probando la funcion con tres
    # casos, no leyendola. Quitar un caracter no necesita una regex.
    texto = texto.replace("*", "")
    texto = texto.replace("—", ", ").replace("–", ", ")   # raya larga y media
    texto = re.sub(r"[ 	]{2,}", " ", texto)
    # La raya sustituida deja un espacio antes de la coma. Se quita SIN grupo de captura: es la
    # tercera vez en esta sesion que una referencia de grupo se pierde al pasar el codigo por el
    # shell y la expresion acaba borrando lo que debia conservar.
    for signo in (",", ".", ";", ":"):
        texto = texto.replace(" " + signo, signo)
    return texto.strip()


def _hoy() -> str:
    return date.today().isoformat()


def preguntas_hoy() -> int:
    return _gastado.get(_hoy(), 0)


def _kpis(negocio: dict) -> str:
    lineas = []
    for k in negocio.get("kpis") or []:
        aviso = {"bad": "  (MAL)", "warn": "  (ojo)"}.get(k.get("alerta"), "")
        lineas.append(f"    {k.get('k')}: {k.get('v')}{aviso}")
    if not lineas and negocio.get("nota"):
        lineas.append("    " + negocio["nota"])
    salud = negocio.get("salud") or {}
    if salud:
        lineas.append(f"    workflows: {salud.get('activos')} activos de {salud.get('total')}, "
                      f"con error {salud.get('errores')}")
    return "\n".join(lineas)


def _ventas(ventas: dict) -> str:
    """Las ventas en texto, no en JSON crudo.

    POR QUE CAMBIO. Primero se pasaba el JSON tal cual "para no decidir por el modelo".
    Resultado: ante un objeto lleno de 0.0 y null, Haiku contesto "no tengo datos de ventas de
    GutLyn" cuando el dato SI estaba y decia CERO. Un cero no es la ausencia de un dato: es una
    respuesta, y en este caso la importante.

    Se escriben las cifras una por linea y se dice explicitamente cuando todo esta a cero.
    """
    r = ventas.get("resumen") or {}
    dias = r.get("period_days", 30)
    lineas = [f"VENTAS DE GUTLYN, ultimos {dias} dias (fuente: Xrise):"]
    for etiqueta, clave, moneda in (
            ("ingresos", "revenue", True), ("de Amazon", "amazon_revenue", True),
            ("de Shopify", "shopify_revenue", True), ("beneficio neto", "net_profit", True),
            ("gasto en publicidad", "ad_spend", True),
            ("devoluciones", "returns_amount", True),
            ("pedidos", "orders", False), ("unidades", "units", False)):
        v = r.get(clave)
        if v is None:
            continue
        lineas.append(f"    {etiqueta}: ${v:,.2f}" if moneda else f"    {etiqueta}: {v}")
    if not r.get("revenue") and not r.get("orders"):
        lineas.append("    TODO A CERO: no falta el dato, es que GutLyn no tiene ninguna venta "
                      "registrada en Xrise en ese periodo. La tienda aun no esta conectada.")
    return "\n".join(lineas)


def _contexto(pendientes: list, colas: list, fallos: list, documentos: list,
              estado: dict | None = None, ventas: dict | None = None) -> str:
    """Todo lo que Zeno sabe, en texto.

    EL ESTADO Y LAS VENTAS ENTRAN AQUI desde el 2026-09-27. Antes solo iban lo pendiente y las
    colas, y el operador pregunto "situacion actual de ventas de GutLyn": el chat contesto que no
    tenia el dato, teniendo Zeno la forma de leerlo. Un asistente que no puede decir como va el
    negocio no es un asistente, es una bandeja.
    """
    partes = []
    if fallos:
        partes.append("FUENTES QUE NO HAN RESPONDIDO (dilo si das numeros): " + " | ".join(fallos))

    for negocio in ((estado or {}).get("zenvrax") or {}).get("negocios") or []:
        partes.append(f"{negocio.get('nombre')} ({negocio.get('sub')}):\n" + _kpis(negocio))

    alertas = [a for a in ((estado or {}).get("gutlyn") or {}).get("alerts") or []
               if a.get("value") and a.get("tone") != "ok"]
    if alertas:
        partes.append("AVISOS DE GUTLYN EN XRISE:\n" + "\n".join(
            f"    {a.get('label')}: {a.get('value')}" for a in alertas))

    if ventas:
        partes.append(_ventas(ventas))

    plan = (estado or {}).get("plan_del_dia") or {}
    foco = plan.get("focus") or {}
    if foco:
        partes.append(f"LO PRIMERO DE HOY: {foco.get('title')} | {foco.get('body') or ''}")

    if colas:
        partes.append("TODO LO PENDIENTE:\n" + "\n".join(
            f"  {c['cuantos']} · {c['titulo']} ({c['negocio']})" for c in colas))
    if pendientes:
        partes.append("LO QUE TOCA AHORA:\n" + "\n".join(
            f"  [{p.negocio}] {p.titulo}" +
            ("  (aprobarlo PUBLICA y no se deshace)" if p.publica_algo else "")
            for p in pendientes[:8]))
    if documentos:
        partes.append("DE LA DOCUMENTACION:\n" + "\n".join(
            f"  {d.get('title') or d.get('doc')}: {(d.get('sub') or '')[:180]}"
            for d in documentos[:4]))
    return "\n\n".join(partes) or "(sin datos: dilo)"


def responde(pregunta: str, pendientes: list, colas: list, fallos: list,
             documentos: list, estado: dict | None = None,
             ventas: dict | None = None) -> dict:
    """Una respuesta y lo que ha costado. Lanza si falta la clave o se alcanzó el tope."""
    if not CLAVE_ANTHROPIC:
        raise SinClaveDeIA("no hay clave de Anthropic configurada")
    hechas = preguntas_hoy()
    if hechas >= TOPE_DIARIO:
        raise TopeAlcanzado(f"{hechas} preguntas hoy, el tope son {TOPE_DIARIO}")

    cuerpo = json.dumps({
        "model": MODELO,
        "max_tokens": 900,
        "temperature": 0.2,          # respuestas con contexto: la tabla de la casa dice 0.2
        "system": SISTEMA,
        "messages": [{"role": "user",
                      "content": f"{_contexto(pendientes, colas, fallos, documentos)}\n\n"
                                 f"PREGUNTA: {pregunta}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=cuerpo, method="POST",
        headers={"content-type": "application/json", "x-api-key": CLAVE_ANTHROPIC,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = json.loads(r.read())

    _gastado[_hoy()] = hechas + 1
    uso = datos.get("usage") or {}
    entrada, salida = uso.get("input_tokens", 0), uso.get("output_tokens", 0)
    coste = entrada / 1e6 * PRECIO_ENTRADA + salida / 1e6 * PRECIO_SALIDA
    texto = "".join(b.get("text", "") for b in datos.get("content", []) if b.get("type") == "text")
    return {
        "respuesta": _limpia(texto),
        "modelo": MODELO,
        "coste_usd": round(coste, 6),
        "preguntas_hoy": _gastado[_hoy()],
        "tope_diario": TOPE_DIARIO,
    }
