# La marca de Zeno

El icono lo eligió el operador el 2026-09-27 entre cuatro propuestas, mirándolas a 140px y a **48px**,
que es el tamaño al que se ven de verdad en la pantalla de inicio.

**Elegida en SEGUNDA vuelta (27-sep): dos barras blancas y la diagonal en ámbar cruzando por
encima, con un hueco de aire a los lados.**

La primera versión (Z blanca con un punto ámbar) la rechazó el operador: *"el logo se ve muy
pobre"*. Tenía razón, y el diagnóstico es concreto: era una Z de tres barras del mismo grosor, sin
ninguna idea dentro. Los dos vecinos sí la tienen, y por eso funcionan: Zenvrax juega con dos pesos
y remata con un punto, y Xrise convierte un brazo de la X en flecha.

La diagonal cruzando es el mismo recurso que el cockpit, donde la X verde pasa sobre las barras
blancas: **dos pesos y dos colores**, que es lo que hace que un glifo se lea de lejos.

```
fondo     negro, esquinas redondeadas al 22%
barras    blancas
diagonal  ambar, por encima y con aire negro a los lados
favicon   la Z entera en ambar, sin aire: a 32px los dos colores se empastan
```

El ámbar se eligió porque **no está en ninguno de los dos iconos existentes**: Zenvrax usa verde
lima y Xrise morado con cian. Los tres van a convivir en la misma pantalla de inicio, y con el
mismo color se tarda en distinguirlos.

## Los iconos no se editan a mano: se generan

```bash
python lab/zeno/marca/genera_iconos.py
```

Produce los cinco que pide una PWA instalable, clonando lo que el cockpit y Xrise ya tienen.

## Tres cosas que salieron de ABRIR los PNG, no de calcularlos

1. **La diagonal salía mucho más fina que las barras.** Estaba hecha con un polígono desplazado en
   horizontal, y en una diagonal de 25 grados el desplazamiento horizontal no es el grosor: hay que
   dividirlo por el seno del ángulo. Se dibuja con `line(width=)`, que da el grosor perpendicular.
2. **El maskable se leía como una C.** Android le recorta un círculo, así que el glifo se mete en la
   zona segura, pero el punto seguía con su tamaño de siempre y se comía la diagonal entera. El
   punto tiene que encogerse **con el glifo**, no con el lienzo.
3. **A 32px el punto no simplifica, destruye.** El favicon quedaba en una mancha donde no se
   distinguía la letra. La versión chica es la **Z entera en ámbar, sin punto**: conserva el color
   de la marca y se lee. Un favicon no es el icono grande reducido.

## Pendiente

El icono **de una PWA ya instalada no se actualiza solo** (pasó con Xrise en septiembre). Cuando
Zeno se despliegue y se instale, cualquier cambio de icono necesita desinstalar y volver a instalar,
o cambiar el `?v=` del manifiesto **y** que el sistema decida refrescar. Por eso el icono se cierra
antes de la primera instalación, no después.
