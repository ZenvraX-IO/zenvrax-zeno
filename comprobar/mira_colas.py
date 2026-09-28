# -*- coding: utf-8 -*-
"""Abrir una cola entera desde Zeno y ver que se puede despachar ahi.

Lo que se comprueba es lo que no se puede leer en el codigo: que la ficha de "44 posts de X" es
tocable, que al tocarla salen los 44 con sus botones, y que pulsar uno pide confirmacion en vez
de disparar. NO se confirma nada: esto no publica.
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

        await pag.goto("https://zeno.zenvrax.com/", wait_until="networkidle")
        await pag.evaluate("t => { try { localStorage.setItem('zeno.token', t); } catch (e) {} }", TOKEN)
        await pag.reload(wait_until="networkidle")
        await pag.wait_for_selector("#app:not([hidden])", timeout=25000)
        await pag.click('.pie button[data-vista="trabajo"]')
        await pag.wait_for_timeout(11000)

        print("1) LAS COLAS QUE SE PUEDEN ABRIR")
        abribles = await pag.locator("[data-cola]").all_inner_texts()
        print("   tocables:", [a.replace("\n", " ").strip() for a in abribles])
        todas = await pag.locator(".ficha").count()
        print(f"   de {todas} fichas en total")
        await pag.screenshot(path=str(FUERA / "colas-lista.png"))
        if not abribles:
            print("   NINGUNA es tocable")
            await nav.close()
            return 1

        print()
        print("2) SE ABRE LA DE CLAIRE")
        # La de X, que es la de 44.
        cual = pag.locator('[data-cola="claire"]')
        if not await cual.count():
            cual = pag.locator("[data-cola]").first
        await cual.click()
        await pag.wait_for_timeout(8000)
        tarjetas = await pag.locator("#cola-cuerpo .tarjeta").count()
        print("   elementos que salen:", tarjetas)
        print("   título de la capa:", await pag.locator("#cola-titulo").inner_text())
        botones = await pag.locator("#cola-cuerpo [data-cola-accion]").count()
        print("   botones de marcar :", botones)
        print("   enlaces           :", await pag.locator('#cola-cuerpo a.b').count())
        print("   botones de copiar :", await pag.locator("#cola-cuerpo [data-copiar]").count())
        print("   textos a la vista :", await pag.locator("#cola-cuerpo .para-pegar").count())
        pasos = await pag.locator("#cola-cuerpo .neg").all_inner_texts()
        print("   pasos distintos   :", sorted({p.replace("ZENVRAX", "").strip()[:28] for p in pasos})[:5])
        await pag.screenshot(path=str(FUERA / "colas-abierta.png"))

        print()
        print("3) PULSAR UN BOTÓN PIDE CONFIRMACIÓN, NO DISPARA")
        if botones:
            await pag.locator("#cola-cuerpo [data-cola-accion]").first.click()
            await pag.wait_for_timeout(2500)
            txt = await pag.locator("#cola-cuerpo .confirmar-aqui").inner_text()
            print("   dice:", " / ".join(txt.split("\n"))[:200] or "(nada)")
            await pag.screenshot(path=str(FUERA / "colas-confirmar.png"))
            visible = await pag.locator("#cola-cuerpo .propuesta").is_visible()
            print("   y se VE dentro de la capa:", visible)

        await nav.close()
        print()
        print("FALLOS:", fallos or "ninguno")
        return 1 if fallos else 0


sys.exit(asyncio.run(main()))
