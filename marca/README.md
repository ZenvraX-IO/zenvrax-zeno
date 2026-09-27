# La marca de Zeno

El icono lo eligió el operador el 2026-09-27 entre cuatro propuestas, mirándolas a 140px y a **48px**,
que es el tamaño al que se ven de verdad en la pantalla de inicio.

**Elegida: la Z blanca con el punto ámbar en el cruce.** El punto no es decorativo: existe en el
icono del cockpit, en el centro de su X, así que es una firma heredada de la casa.

```
fondo     negro (#101012), esquinas redondeadas al 22%
glifo     Z de trazo grueso, blanco (#F5F5F5)
firma     punto ámbar (#F0A830) en el cruce
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
