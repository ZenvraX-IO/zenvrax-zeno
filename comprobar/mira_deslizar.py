# -*- coding: utf-8 -*-
"""Deslizar un correo para quitarlo, en un movil de verdad y contra produccion.

LO QUE UN TEST NO PUEDE DECIR. Que el codigo del gesto este escrito no significa que el dedo lo
dispare: el umbral puede quedar corto, el scroll puede robarle el movimiento, o el clic del enlace
puede colarse y abrir Gmail en vez de quitar el correo. Eso solo se ve arrastrando.

TOCA UN DATO REAL: esconde un correo en la lista de Zeno. No toca Gmail (el correo sigue intacto y
sin leer), y al acabar lo devuelve, asi que la bandeja queda como estaba.
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
        # Una pestaña nueva al abrir el correo seria el fallo de "arrastrar abre Gmail": se apunta.
        abiertas = []
        ctx.on("page", lambda pg: abiertas.append(pg.url))

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.evaluate("t => localStorage.setItem('zeno.token', t)", TOKEN)
        await pag.reload(wait_until="domcontentloaded")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)
        await pag.click('.pie button[data-vista="personal"]')
        await pag.wait_for_timeout(24000)

        antes = await pag.locator("[data-desliza]").count()
        print("correos que se pueden deslizar:", antes)
        if not antes:
            print("no hay correo con el que probar")
            await nav.close()
            return 1
        cual = await pag.locator("[data-desliza] .correo .as").first.inner_text()
        print("se va a deslizar:", cual[:52])

        # ------------------------------------------------------------ el gesto, con el dedo
        caja = pag.locator("[data-desliza]").first
        c = await caja.bounding_box()
        y = c["y"] + c["height"] / 2
        # NADA DE UN TAP PREVIO. La primera version daba un toque "para despertar el listener" y
        # ese toque, el solo, abre el correo en Gmail: el comprobador se acusaba a si mismo. La
        # herramienta de medida se mira antes que el codigo.

        # Playwright no tiene "arrastrar con el dedo": se hace con los eventos de puntero, que son
        # los que el codigo escucha de verdad.
        await pag.evaluate("""([x, y]) => {
          const el = document.elementFromPoint(x, y);
          const caja = el.closest("[data-desliza]");
          const ev = (t, cx) => caja.dispatchEvent(new PointerEvent(t, {
            clientX: cx, clientY: y, bubbles: true, pointerId: 1, button: 0}));
          ev("pointerdown", x);
          for (let i = 1; i <= 12; i++) ev("pointermove", x - i * 12);
          ev("pointerup", x - 144);
        }""", [c["x"] + c["width"] - 30, y])
        await pag.wait_for_timeout(3500)

        despues = await pag.locator("[data-desliza]").count()
        print()
        print(f"tarjetas antes: {antes} · despues: {despues}")
        sigue = cual[:40] in (await pag.locator("#lista-correos").inner_text())
        print("el correo deslizado sigue en la lista:", "SI, MAL" if sigue else "no")
        if despues != antes - 1 or sigue:
            mal.append("el gesto no ha quitado el correo")

        deshacer = await pag.locator("#ver-ocultos").count()
        print("aparece el deshacer:", bool(deshacer))
        if not deshacer:
            mal.append("no sale el boton de devolver")
        else:
            print("   dice:", await pag.locator("#ver-ocultos").inner_text())
        print("pestañas abiertas por el gesto:", abiertas or "ninguna (bien)")
        if abiertas:
            mal.append(f"arrastrar ha abierto {abiertas}")
        await pag.screenshot(path=str(FUERA / "deslizar-1-quitado.png"), full_page=True)

        # ------------------------------------------------------------ y se devuelve
        if deshacer:
            await pag.click("#ver-ocultos")
            await pag.wait_for_timeout(22000)
            vuelta = await pag.locator("[data-desliza]").count()
            print()
            print(f"tras devolver: {vuelta} tarjetas (deberia ser {antes})")
            if vuelta != antes:
                mal.append(f"no han vuelto todos: {vuelta} de {antes}")
            await pag.screenshot(path=str(FUERA / "deslizar-2-devuelto.png"), full_page=True)

        await nav.close()
    print()
    print("ERRORES DE LA PAGINA:", fallos or "ninguno")
    print("FALLOS:", mal or "ninguno")
    return 1 if (mal or fallos) else 0


sys.exit(asyncio.run(main()))
