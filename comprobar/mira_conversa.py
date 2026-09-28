# -*- coding: utf-8 -*-
"""La conversacion por voz, en un navegador de verdad.

El microfono no se puede fingir, asi que se sustituye el motor de reconocimiento por uno de
mentira que devuelve las frases que se le digan. Todo lo demas es el codigo real: la puerta de
ordenes, la confirmacion, la ejecucion y la voz de salida.

Lo que se comprueba es lo que no se puede leer en el CSS: que el bucle avanza, que confirma
antes de tocar nada y que lo que publica no se hace hablando.
"""
import asyncio
import io
import os
import pathlib
import sys

from playwright.async_api import async_playwright

TOKEN, FUERA = sys.argv[1], pathlib.Path(sys.argv[2])
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Un reconocimiento de mentira: entrega la siguiente frase de la cola. Y una sintesis de mentira
# que apunta lo que Zeno dice en alto, para poder leerlo despues.
FINGIDO = """
window.__dicho = [];
window.__cola = [];
class FalsoMotor {
  constructor() { this.onresult = null; this.onerror = null; this.onend = null; }
  start() {
    const frase = window.__cola.shift();
    setTimeout(() => {
      if (frase !== undefined && this.onresult)
        this.onresult({ resultIndex: 0,
                        results: [Object.assign([{ transcript: frase }], { 0: { transcript: frase }, isFinal: true, length: 1 })] });
      if (this.onend) this.onend();
    }, 120);
  }
  stop() { if (this.onend) this.onend(); }
}
window.SpeechRecognition = FalsoMotor;
window.webkitSpeechRecognition = FalsoMotor;
Object.defineProperty(window, "speechSynthesis", {
  configurable: true,
  value: { cancel() {}, speak(u) { window.__dicho.push(u.text); setTimeout(() => u.onend && u.onend(), 40); } },
});
window.SpeechSynthesisUtterance = function (t) { this.text = t; };
"""


async def main():
    FUERA.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        nav = await p.chromium.launch()
        ctx = await nav.new_context(viewport={"width": 390, "height": 844},
                                    device_scale_factor=2, has_touch=True, is_mobile=True)
        await ctx.add_init_script(f'try {{ localStorage.setItem("zeno.token", {TOKEN!r}); }} catch (e) {{}}')
        await ctx.add_init_script(FINGIDO)
        pag = await ctx.new_page()
        fallos = []
        pag.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
        pag.on("console", lambda m: fallos.append(f"console.error: {m.text}") if m.type == "error" else None)

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)
        await pag.click("#btn-chat")
        await pag.wait_for_timeout(1200)

        async def conversacion(frases, espera=9000):
            await pag.evaluate("f => { window.__cola = f; window.__dicho = []; }", frases)
            await pag.click("#mic-pregunta")
            await pag.wait_for_timeout(espera)
            dicho = await pag.evaluate("window.__dicho")
            burbujas = await pag.locator("#burbujas > div").all_inner_texts()
            return dicho, burbujas

        print("1) UNA ORDEN AMBIGUA: tres tareas hablan de la landing")
        dicho, _ = await conversacion(["marca hecha la tarea de la landing", ""])
        print("   Zeno dice:", " | ".join(d[:90] for d in dicho) or "(nada)")

        print()
        print("2) UNA ORDEN CLARA, Y SE DICE QUE NO")
        dicho, burbujas = await conversacion(["marca hecha la tarea de la presentacion", "no, dejalo", ""])
        print("   Zeno dice:", " | ".join(d[:70] for d in dicho) or "(nada)")
        print("   ultima burbuja:", burbujas[-1][:70] if burbujas else "(ninguna)")

        print()
        print("3) UNA ORDEN CLARA, Y SE DICE QUE SI: tiene que cerrarla de verdad")
        # OJO: este paso necesita que exista una tarea de prueba llamada asi. Si no existe, la
        # orden no encaja, el "si, hazlo" cae al chat como si fuera una pregunta y GASTA sin que
        # nadie lo haya autorizado. Paso de verdad: 0,0017 USD en un ensayo que se creia gratis.
        if os.environ.get("PERMITIR_GASTO_API") != "1":
            print("   saltado: sin la tarea de prueba creada, esto acabaria preguntando al chat")
            print("   (créala primero, o pásalo con el permiso de gasto delante)")
            dicho, burbujas = [], []
        else:
            dicho, burbujas = await conversacion(["cierra lo del zapato azul", "si, hazlo", ""], espera=14000)
        if dicho or burbujas:
            print("   Zeno dice:", " | ".join(d[:70] for d in dicho) or "(nada)")
            print("   ultima burbuja:", burbujas[-1][:70] if burbujas else "(ninguna)")

        print()
        # El paso 4 es el UNICO que gasta: una pregunta al chat es una llamada a Haiku. Los dos de
        # arriba pasan por /api/orden, que empareja con reglas y cuesta cero.
        if os.environ.get("PERMITIR_GASTO_API") != "1":
            print("4) LA PREGUNTA AL CHAT: no se hace, cuesta 1 llamada de Haiku (~0,0005 USD)")
            await pag.screenshot(path=str(FUERA / "conversacion.png"))
            await nav.close()
            print()
            print("FALLOS:", fallos or "ninguno")
            return 1 if fallos else 0
        print("4) UNA PREGUNTA: tiene que irse al chat y contestar hablando")
        dicho, burbujas = await conversacion(["cuantas tareas tengo pendientes", ""], espera=22000)
        print("   Zeno dice:", (dicho[0][:130] + "…") if dicho else "(no ha hablado)")

        await pag.screenshot(path=str(FUERA / "conversacion.png"))
        await nav.close()
        print()
        print("FALLOS:", fallos or "ninguno")
        return 1 if fallos else 0


sys.exit(asyncio.run(main()))
