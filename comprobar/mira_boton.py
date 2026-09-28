# -*- coding: utf-8 -*-
"""Mira la pantalla de Trabajo en un movil y comprueba que el boton de cerrar tareas esta ahi.

Entra con un token inyectado en localStorage en vez de la contraseña: lo que se verifica es la
pantalla, no el login, y la contraseña del operador no tiene que pasar por aqui.
"""
import asyncio
import io
import pathlib
import sys

from playwright.async_api import async_playwright

TOKEN = sys.argv[1]
FUERA = pathlib.Path(sys.argv[2])

# La consola de Windows es cp1252 y un emoji en un aviso la revienta a mitad del informe.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def main():
    FUERA.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        nav = await p.chromium.launch()
        ctx = await nav.new_context(viewport={"width": 390, "height": 844},
                                    device_scale_factor=2, has_touch=True, is_mobile=True)
        await ctx.add_init_script(f'try {{ localStorage.setItem("zeno.token", {TOKEN!r}); }} catch (e) {{}}')
        pag = await ctx.new_page()
        fallos = []
        pag.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
        pag.on("console", lambda m: fallos.append(f"console.error: {m.text}") if m.type == "error" else None)

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)
        await pag.click('.pie button[data-vista="trabajo"]')
        await pag.wait_for_timeout(9000)
        await pag.screenshot(path=str(FUERA / "trabajo.png"), full_page=True)

        botones = await pag.locator("[data-aviso]").all_inner_texts()
        print("  botones de aviso en pantalla:", botones)
        cuerpos = await pag.locator(".tarjeta .extracto").all_inner_texts()
        print("  avisos con cuerpo:", len(cuerpos), cuerpos[:3])

        # El camino que recorre el dedo: pulsar y ver la confirmacion, SIN confirmarla.
        if botones:
            await pag.locator("[data-aviso]").first.click()
            await pag.wait_for_timeout(2500)
            await pag.screenshot(path=str(FUERA / "confirmacion.png"))
            txt = await pag.locator(".confirmar-aqui").first.inner_text()
            print("  la confirmacion dice:", " / ".join(txt.split("\n"))[:220])

        await nav.close()
        print("FALLOS:", fallos or "ninguno")
        return 1 if fallos else 0


sys.exit(asyncio.run(main()))
