# -*- coding: utf-8 -*-
"""El icono de Zeno. Se GENERA, nunca se edita a mano.

    python lab/zeno/marca/genera_iconos.py

EL DISEÑO, elegido por el operador el 2026-09-27 en segunda vuelta: dos barras blancas y la
diagonal en AMBAR cruzando por encima, con un hueco de aire a los lados.

Es el mismo recurso que usa el icono del cockpit, donde la X verde cruza sobre las barras blancas:
dos pesos y dos colores, que es lo que hace que un glifo se lea de lejos. La primera version era una
Z de tres barras del mismo grosor, y el operador la rechazo con razon: *"el logo se ve muy pobre"*.
No tenia ninguna idea dentro, mientras que Zenvrax juega con dos pesos y un punto, y Xrise convierte
un brazo de la X en flecha.

El AMBAR no esta en ninguno de los dos iconos vecinos (Zenvrax es verde lima, Xrise morado y cian),
asi que los tres se distinguen en la misma pantalla de inicio.

TRES COSAS QUE SALIERON DE ABRIR LOS PNG, no de calcularlos:

1. La diagonal salia mas fina que las barras cuando se dibujaba con un poligono desplazado en
   horizontal: en una diagonal de 25 grados, ese desplazamiento no es el grosor. Se dibuja con
   `line(width=)`, que si da el grosor perpendicular.
2. El maskable se leia como una C. Android le recorta un circulo, asi que el glifo se mete en la
   zona segura; el hueco de aire tiene que encogerse CON el, no quedarse con su tamaño de siempre.
3. A 32px el aire negro alrededor de la diagonal se come la letra, asi que el favicon se
   SIMPLIFICA (barras mas gordas, menos margen, hueco fino) pero NO cambia de colores. La primera
   version salio entera en ambar sobre fondo ambar, y en la pestaña se leia como otra marca
   distinta a la del icono grande. El operador (2026-09-27): *"tambien favicon y logo
   incorrectos"*. Un icono que cambia de aspecto segun el tamaño deja de ser un icono.
"""
from PIL import Image, ImageDraw

E = 6                      # se dibuja a 6x y se reduce: la diagonal pide muestreo
NEGRO = (16, 16, 18)
BLANCO = (247, 247, 249)
AMBAR = (240, 168, 48)

#: Lo que hace falta para una PWA instalable, clonado del cockpit y de Xrise.
JUEGO = [
    ("icon-192.png", 192, False),
    ("icon-512.png", 512, False),
    ("icon-512-maskable.png", 512, True),   # Android le recorta un circulo
    ("apple-touch-icon.png", 180, False),
    ("favicon.png", 32, False),
    ("favicon-64.png", 64, False),      # el navegador elige el mas nitido de los dos
]


def zeno(lado: int = 192, maskable: bool = False) -> Image.Image:
    img = Image.new("RGBA", (lado * E, lado * E), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    caja = [0, 0, lado * E - 1, lado * E - 1]
    if maskable:
        d.rectangle(caja, fill=NEGRO)      # el fondo llena el cuadrado: el sistema recorta
    else:
        d.rounded_rectangle(caja, radius=int(lado * E * 0.22), fill=NEGRO)

    chico = lado <= 64
    margen = 54 if maskable else (14 if chico else 40)
    k = lado / 192 * E
    encoge = (192 - 2 * margen) / 112.0
    g = 24 * k * encoge
    i, f = margen * k, (192 - margen) * k
    a, b = margen * k, (192 - margen) * k

    # LOS COLORES NO CAMBIAN CON EL TAMAÑO. Lo que cambia es el detalle: en chico las barras van
    # mas gordas, el margen es menor y el aire alrededor de la diagonal se reduce a lo justo para
    # que se siga leyendo la separacion. Cambiar los colores hacia que la pestaña enseñara una
    # marca y la pantalla de inicio otra.
    if chico:
        g *= 1.18
    d.rectangle([i, a, f, a + g], fill=BLANCO)
    d.rectangle([i, b - g, f, b], fill=BLANCO)

    extremos = [(f - g / 2, a + g / 2), (i + g / 2, b - g / 2)]
    # El aire alrededor de la diagonal: es lo que separa los dos pesos y hace que la Z se lea.
    d.line(extremos, fill=NEGRO, width=int(g * (1.45 if chico else 1.95)))
    d.line(extremos, fill=AMBAR, width=int(g))
    return img.resize((lado, lado), Image.LANCZOS)


if __name__ == "__main__":
    for nombre, lado, maskable in JUEGO:
        zeno(lado, maskable).save(nombre)
        print("  ", nombre, f"{lado}x{lado}")
