# -*- coding: utf-8 -*-
"""Entrar con Face ID, de punta a punta, sin un iPhone.

Chromium trae un autenticador VIRTUAL por el protocolo de DevTools: se comporta como el chip de
un telefono, firma de verdad y el servidor comprueba esa firma de verdad. Lo unico fingido es el
dedo o la cara que lo desbloquea.

Asi que esto prueba lo que de verdad importa y no se puede leer en el codigo: que el alta guarda
una credencial que el servidor sabe verificar, que entrar con ella emite una sesion buena, y que
una credencial de otro autenticador NO entra.
"""
import asyncio
import io
import pathlib
import sys

from playwright.async_api import async_playwright

CLAVE_O_TOKEN, FUERA = sys.argv[1], pathlib.Path(sys.argv[2])
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def autenticador(cdp, verificado=True):
    """Un telefono de mentira que firma de verdad."""
    await cdp.send("WebAuthn.enable")
    r = await cdp.send("WebAuthn.addVirtualAuthenticator", {
        "options": {"protocol": "ctap2", "transport": "internal",
                    "hasResidentKey": True, "hasUserVerification": True,
                    "isUserVerified": verificado, "automaticPresenceSimulation": True}})
    return r["authenticatorId"]


async def main():
    FUERA.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        nav = await p.chromium.launch()
        ctx = await nav.new_context(viewport={"width": 390, "height": 844},
                                    device_scale_factor=2, has_touch=True, is_mobile=True)
        # El token se pone UNA vez y a mano, no con un init script. Con init script se reinyecta
        # en cada carga, asi que los pasos de abajo entraban por la sesion guardada y no por la
        # cara: la prueba daba verde sin probar nada. Paso, y se vio porque el telefono AJENO
        # tambien "entraba".
        pag = await ctx.new_page()
        fallos = []
        pag.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
        pag.on("console", lambda m: fallos.append(f"console.error: {m.text}") if m.type == "error" else None)

        cdp = await ctx.new_cdp_session(pag)
        ident = await autenticador(cdp)
        print("  telefono virtual conectado")

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.evaluate("t => { try { localStorage.setItem('zeno.token', t); } catch (e) {} }",
                           CLAVE_O_TOKEN)
        await pag.reload(wait_until="networkidle")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)

        print()
        print("1) ESTANDO DENTRO, SE OFRECE ACTIVARLO")
        try:
            await pag.wait_for_selector("#cara-si", timeout=12000)
            print("   sale la tarjeta: sí")
        except Exception:
            print("   sale la tarjeta: NO (¿ya hay una cara dada de alta?)")
            await nav.close()
            return 1

        await pag.screenshot(path=str(FUERA / "cara-ofrecer.png"))
        await pag.click("#cara-si")
        await pag.wait_for_timeout(4000)
        texto = await pag.locator("#cara-si, .tarjeta .post").first.inner_text()
        estado = await pag.evaluate("fetch('/api/rostro').then(r => r.json())")
        print("   despues de activarlo, el servidor dice:", estado)
        await pag.screenshot(path=str(FUERA / "cara-activada.png"))
        if not estado.get("hay"):
            print("   NO SE HA DADO DE ALTA")
            await nav.close()
            return 1

        print()
        print("2) SALIR Y ENTRAR SOLO CON LA CARA")
        await pag.evaluate("try { localStorage.clear(); } catch (e) {}")
        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.wait_for_timeout(1500)
        visible = await pag.locator("#btn-cara").is_visible()
        print("   sale el botón de Face ID:", visible)
        await pag.screenshot(path=str(FUERA / "cara-login.png"))
        try:
            await pag.wait_for_selector("#app:not([hidden])", timeout=15000)
            print("   ha entrado sin escribir nada: sí")
        except Exception:
            print("   NO ha entrado")
            print("   el login dice:", await pag.locator("#error-login").inner_text())
            await nav.close()
            return 1

        print()
        print("3) OTRO TELÉFONO, QUE NO ESTÁ DADO DE ALTA, NO ENTRA")
        await cdp.send("WebAuthn.removeVirtualAuthenticator", {"authenticatorId": ident})
        await autenticador(cdp)
        await pag.evaluate("try { localStorage.clear(); } catch (e) {}")
        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.wait_for_timeout(7000)
        dentro = await pag.locator("#app").is_visible()
        print("   ha entrado el teléfono ajeno:", "SÍ, MAL" if dentro else "no")
        await pag.screenshot(path=str(FUERA / "cara-ajeno.png"))

        await nav.close()
        print()
        print("FALLOS:", fallos or "ninguno")
        return 1 if (fallos or dentro) else 0


sys.exit(asyncio.run(main()))
