# -*- coding: utf-8 -*-
"""Mira los dos botones de dictar en un movil de verdad: que salgan, y que escuchen.

Chromium de Playwright trae SpeechRecognition, asi que se puede comprobar hasta que el boton se
pone en escucha. La transcripcion real necesita un microfono y no se puede fingir aqui: eso se
prueba hablandole al telefono.
"""
import asyncio
import io
import pathlib
import sys

from playwright.async_api import async_playwright

TOKEN, FUERA = sys.argv[1], pathlib.Path(sys.argv[2])
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def main():
    FUERA.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        nav = await p.chromium.launch(args=["--use-fake-ui-for-media-stream"])
        ctx = await nav.new_context(viewport={"width": 390, "height": 844},
                                    device_scale_factor=2, has_touch=True, is_mobile=True,
                                    permissions=["microphone"])
        await ctx.add_init_script(f'try {{ localStorage.setItem("zeno.token", {TOKEN!r}); }} catch (e) {{}}')
        pag = await ctx.new_page()
        fallos = []
        pag.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
        pag.on("console", lambda m: fallos.append(f"console.error: {m.text}") if m.type == "error" else None)

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)

        print("  el navegador sabe escuchar:",
              await pag.evaluate("!!(window.SpeechRecognition || window.webkitSpeechRecognition)"))

        await pag.click("#btn-buscar")
        await pag.wait_for_timeout(1200)
        print("  boton en BUSCAR visible:", await pag.locator("#mic-q").is_visible())
        await pag.click("#mic-q")
        await pag.wait_for_timeout(1500)
        print("   al pulsar, en escucha:", "oyendo" in (await pag.locator("#mic-q").get_attribute("class")),
              "| dice:", repr(await pag.locator("#dice-q").inner_text()))
        await pag.screenshot(path=str(FUERA / "voz-buscar.png"))
        await pag.click("#mic-q")            # parar
        await pag.wait_for_timeout(800)
        print("   al volver a pulsar, para:", "oyendo" not in (await pag.locator("#mic-q").get_attribute("class")))
        await pag.click('[data-cerrar="capa-buscar"]')

        await pag.click("#btn-chat")
        await pag.wait_for_timeout(1500)
        print("  boton en PREGUNTAR visible:", await pag.locator("#mic-pregunta").is_visible())
        # Lo dictado se añade a lo tecleado: se teclea primero y se comprueba que no se pisa.
        await pag.fill("#pregunta", "cuanto")
        await pag.click("#mic-pregunta")
        await pag.wait_for_timeout(1200)
        print("   en escucha con texto ya escrito:",
              "oyendo" in (await pag.locator("#mic-pregunta").get_attribute("class")),
              "| el campo sigue diciendo:", repr(await pag.locator("#pregunta").input_value()))
        await pag.screenshot(path=str(FUERA / "voz-chat.png"))

        await nav.close()
        print("FALLOS:", fallos or "ninguno")
        return 1 if fallos else 0


sys.exit(asyncio.run(main()))
