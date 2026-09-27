# -*- coding: utf-8 -*-
"""La opcion C elegida por el operador, afinada para que aguante los 48px.

Al ensenarle las cuatro le dije que en la C el punto casi desaparece a 48px, que es el tamano al que
se mira en la pantalla de inicio. Eligio la C, asi que el trabajo ahora es que eso deje de ser
verdad, no repetir la pega: el punto crece, el anillo que lo separa de la Z se ajusta para que no
parta la diagonal, y se comprueba ABRIENDO el png a 48, no calculandolo.
"""
from PIL import Image, ImageDraw

E = 4
NEGRO = (16, 16, 18)
BLANCO = (245, 245, 245)
AMBAR = (240, 168, 48)


def zeno(lado=192, punto=13, anillo=20, maskable=False):
    """El icono. `punto` y `anillo` en unidades de 192 para poder probar tamanos."""
    img = Image.new("RGBA", (lado * E, lado * E), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    caja = [0, 0, lado * E - 1, lado * E - 1]
    if maskable:
        # maskable: el sistema recorta un circulo, asi que el fondo llena el cuadrado entero y el
        # glifo se encoge para caber en la zona segura (el 80% central).
        d.rectangle(caja, fill=NEGRO)
    else:
        d.rounded_rectangle(caja, radius=int(lado * E * 0.22), fill=NEGRO)

    k = lado / 192.0
    if maskable:
        margen = 54          # Android le recorta un circulo: el glifo se mete en la zona segura
    elif lado <= 48:
        # A 32px el margen normal se come la letra. Los favicon se dibujan mas llenos a proposito:
        # no son el icono grande reducido, son una version simplificada.
        margen = 16
    else:
        margen = 40
    # El punto tiene que encogerse CON el glifo, no con el lienzo. Sin esto, el maskable salia con
    # la Z reducida y el punto del tamano de siempre: se comia la diagonal entera y la letra se leia
    # como una C. Se vio abriendo el PNG de 512, no calculandolo.
    encoge = (192 - 2 * margen) / (192 - 2 * 40)
    g = int(24 * k * E * encoge)
    i, f = int(margen * k * E), int((192 - margen) * k * E)
    a, b = int(margen * k * E), int((192 - margen) * k * E)
    tinta = AMBAR if lado <= 48 else BLANCO
    d.rectangle([i, a, f, a + g], fill=tinta)
    d.rectangle([i, b - g, f, b], fill=tinta)
    d.line([(f - g // 2, a + g // 2), (i + g // 2, b - g // 2)], fill=tinta, width=g)

    if lado <= 48:
        # A 32px el punto no simplifica, DESTRUYE: se come la diagonal y la Z queda en una mancha.
        # Abierto a ese tamano no se distinguia la letra. La version chica es la Z entera en ambar,
        # que conserva el color de la marca y se lee. Comprobado abriendo los tres candidatos.
        return img.resize((lado, lado), Image.LANCZOS)
    centro = (lado * E // 2, lado * E // 2)
    for radio, color in ((int(anillo * k * E * encoge), NEGRO),
                         (int(punto * k * E * encoge), AMBAR)):
        d.ellipse([centro[0] - radio, centro[1] - radio, centro[0] + radio, centro[1] + radio],
                  fill=color)
    return img.resize((lado, lado), Image.LANCZOS)


#: El tamano de punto elegido: 17 sobre 192. Se probaron 13, 17 y 21 mirando los PNG a 48px, que es
#: como se ve en la pantalla de inicio. Con 13 el punto casi no esta; con 21 se come la diagonal y la
#: Z se parte en dos. Con 17 se ve y la letra sigue entera.
PUNTO, ANILLO = 17, 25

#: Lo que hace falta para una PWA instalable, clonado del cockpit y de Xrise, que ya lo tienen.
JUEGO = [
    ("icon-192.png", 192, False),
    ("icon-512.png", 512, False),
    ("icon-512-maskable.png", 512, True),   # Android le recorta un circulo: glifo mas adentro
    ("apple-touch-icon.png", 180, False),
    ("favicon.png", 32, False),
]

if __name__ == "__main__":
    for nombre, lado, maskable in JUEGO:
        zeno(lado, PUNTO, ANILLO, maskable).save(nombre)
        print("  ", nombre, f"{lado}x{lado}")
