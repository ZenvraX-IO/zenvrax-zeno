# -*- coding: utf-8 -*-
"""Que se pueda CERRAR la puerta desde el propio movil, no solo abrirla.

Los dos endpoints de baja existian desde el primer dia sin ningun boton que los llamara. Esto
comprueba el ciclo entero con el autenticador virtual de Chromium: activar el Face ID, verlo en el
servidor, darlo de baja desde la pantalla, y ver que el servidor se queda sin ninguna cara.
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
        nav = await p.chromium.launch()
        ctx = await nav.new_context(viewport={"width": 390, "height": 844},
                                    device_scale_factor=2, has_touch=True, is_mobile=True)
        pag = await ctx.new_page()
        fallos = []
        pag.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
        pag.on("console", lambda m: fallos.append(f"console.error: {m.text}") if m.type == "error" else None)

        cdp = await ctx.new_cdp_session(pag)
        await cdp.send("WebAuthn.enable")
        await cdp.send("WebAuthn.addVirtualAuthenticator", {
            "options": {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                        "hasUserVerification": True, "isUserVerified": True,
                        "automaticPresenceSimulation": True}})

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.evaluate("t => { try { localStorage.setItem('zeno.token', t); } catch (e) {} }", TOKEN)
        await pag.reload(wait_until="networkidle")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)

        # La caja vive al final de HOY, debajo de lo urgente. (La primera version de esta prueba
        # miraba en Personal y el boton "existia pero no era visible": estaba en otra pestaña.)
        await pag.wait_for_timeout(9000)
        await pag.screenshot(path=str(FUERA / "bajas-antes.png"), full_page=False)

        print("1) LOS DOS BOTONES ESTÁN EN LA PANTALLA")
        for sel, que in (("#cara-on, #cara-off", "Face ID"), ("#avisos-on, #avisos-off", "avisos")):
            print(f"   {que}: {await pag.locator(sel).count()} botón(es) visibles:",
                  await pag.locator(sel).first.is_visible() if await pag.locator(sel).count() else "-")
        print("   lo que dice la caja:", " / ".join(
            (await pag.locator("#caja-avisos .avisos .c").all_inner_texts()) or ["(vacía)"]))

        print()
        print("2) ACTIVAR EL FACE ID Y DARLO DE BAJA")
        if await pag.locator("#cara-on").count():
            await pag.click("#cara-on")
            await pag.wait_for_timeout(4000)
        print("   el servidor dice:", await pag.evaluate("fetch('/api/rostro').then(r => r.json())"))
        await pag.screenshot(path=str(FUERA / "bajas-activo.png"))

        # El aviso de confirmar se acepta solo: aqui se prueba que la baja funciona, no el dialogo.
        pag.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        if await pag.locator("#cara-off").count():
            await pag.click("#cara-off")
            await pag.wait_for_timeout(3500)
        else:
            print("   NO SALE el botón de dar de baja")
        despues = await pag.evaluate("fetch('/api/rostro').then(r => r.json())")
        print("   después de darlo de baja:", despues)
        await pag.screenshot(path=str(FUERA / "bajas-despues.png"))

        await nav.close()
        print()
        print("FALLOS:", fallos or "ninguno")
        return 1 if (fallos or despues.get("hay")) else 0


sys.exit(asyncio.run(main()))
