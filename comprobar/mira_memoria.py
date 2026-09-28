# -*- coding: utf-8 -*-
"""La memoria de Zeno, en un movil de verdad y contra produccion.

Lo que no pueden decir los tests: que el apunte se guarda al decirlo, que la conversacion sigue
donde la dejaste DESPUES de cerrar la aplicacion, y que se puede borrar desde el telefono.

NO GASTA NADA. El camino que se prueba ("recuerda que...") se reconoce con reglas y no llega al
modelo, que es justo lo que hay que verificar: si algun dia pasara por Haiku, aqui saldria un
coste distinto de cero y el guion lo diria.

DEJA LAS COSAS COMO ESTABAN: el apunte que crea lo borra al final, y solo toca el hilo de la
conversacion si estaba vacio al empezar.
"""
import asyncio
import io
import pathlib
import sys

from playwright.async_api import async_playwright

TOKEN, FUERA = sys.argv[1], pathlib.Path(sys.argv[2])
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FRASE = "recuerda que esto es una prueba de la memoria y se puede borrar"


async def main():
    FUERA.mkdir(parents=True, exist_ok=True)
    mal = []
    async with async_playwright() as p:
        nav = await p.chromium.launch()
        ctx = await nav.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                    has_touch=True, device_scale_factor=2)
        pag = await ctx.new_page()
        fallos = []
        pag.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
        pag.on("console", lambda m: fallos.append(f"console.error: {m.text}")
               if m.type == "error" else None)

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.evaluate("t => localStorage.setItem('zeno.token', t)", TOKEN)
        await pag.reload(wait_until="domcontentloaded")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)

        # ---------------------------------------------------------------- 1. apuntar
        await pag.wait_for_selector("#btn-chat", state="visible", timeout=30000)
        await pag.click("#btn-chat", force=True)
        await pag.wait_for_timeout(2500)
        await pag.fill("#pregunta", FRASE)
        await pag.press("#pregunta", "Enter")
        await pag.wait_for_timeout(3000)
        dicho = await pag.locator("#burbujas .el").last.inner_text()
        coste = await pag.locator("#burbujas .coste").last.inner_text()
        print("1. lo que contesta :", dicho)
        print("   el coste        :", coste)
        if not dicho.lower().startswith("apuntado"):
            mal.append("no lo apunto: " + dicho)
        if "$0.0000" not in coste:
            mal.append("HA GASTADO API por un apunte: " + coste)
        await pag.screenshot(path=str(FUERA / "memoria-1-apuntado.png"))

        # ---------------------------------------------------------------- 2. cerrar y volver
        # Recargar es lo mas parecido a cerrar la aplicacion: se pierde todo lo que estaba en
        # pantalla, y lo unico que puede traer la conversacion de vuelta es el servidor.
        await pag.reload(wait_until="domcontentloaded")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)
        await pag.wait_for_selector("#btn-chat", state="visible", timeout=30000)
        await pag.click("#btn-chat", force=True)
        await pag.wait_for_timeout(3500)
        texto = await pag.locator("#burbujas").inner_text()
        print("2. al volver, el chat empieza con:",
              " / ".join(texto.split("\n")[:3])[:140])
        if "lo último que hablamos" not in texto:
            mal.append("la conversacion NO se retoma al volver")
        if FRASE not in texto:
            mal.append("lo hablado no ha vuelto")
        await pag.screenshot(path=str(FUERA / "memoria-2-retomada.png"))

        # ---------------------------------------------------------------- 3. la pantalla
        await pag.click('[data-cerrar="capa-chat"]')
        await pag.wait_for_timeout(1200)
        await pag.click('.pie button[data-vista="hoy"]')
        await pag.wait_for_timeout(9000)
        caja = pag.locator("#caja-avisos")
        await caja.scroll_into_view_if_needed()
        visto = await caja.inner_text()
        print("3. en los ajustes  :", " / ".join(visto.split("\n"))[:200])
        if "Lo que recuerdo" not in visto:
            mal.append("no hay pantalla para ver la memoria")
        if "prueba de la memoria" not in visto:
            mal.append("el apunte no sale en la pantalla")
        await pag.screenshot(path=str(FUERA / "memoria-3-pantalla.png"), full_page=True)

        # ---------------------------------------------------------------- 4. borrar
        await pag.locator("#caja-avisos [data-olvidar]").last.click()
        await pag.wait_for_timeout(5000)
        despues = await pag.locator("#caja-avisos").inner_text()
        print("4. tras borrar     :", "sigue ahi, MAL" if "prueba de la memoria" in despues
              else "desaparecido")
        if "prueba de la memoria" in despues:
            mal.append("el boton de borrar no borra")
        await pag.screenshot(path=str(FUERA / "memoria-4-borrado.png"), full_page=True)

        await nav.close()

    print()
    print("ERRORES DE LA PAGINA:", fallos or "ninguno")
    print("FALLOS:", mal or "ninguno")
    return 1 if (mal or fallos) else 0


sys.exit(asyncio.run(main()))
