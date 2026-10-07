# Zeno — el asistente

**STATUS:** `graduated` — repo propio desde el 2026-09-28, con su historia (97 commits).
**Abierto:** 2026-09-27 · **En producción:** [zeno.zenvrax.com](https://zeno.zenvrax.com)

## Dónde vive cada cosa

Zeno es una **fachada**: lee el cockpit (`zenvrax-io/`) y Xrise (`zenvrax-xrise/`), que son repos
hermanos, y no guarda datos de negocio propios. El único estado suyo es el volumen `zeno-datos`
(el permiso cifrado de Google, los avisos y el diario).

El catálogo de acciones se **recolecta leyendo el código** de los otros dos, así que para
regenerarlo hacen falta los tres repos al lado. Dentro del contenedor viaja congelado
(`catalogo/congelado.json`), que es lo que hace que funcione sin ellos.

```
zenvrax-io/        el cockpit, y donde nació Zeno
zenvrax-xrise/     GutLyn y Claire
zenvrax-zeno/      esto
```
**Plan:** [plan del asistente](../../docs/PLAN-ASISTENTE.md)

## Qué sabe hacer hoy, medido contra producción el 2026-09-28

| | estado |
|---|---|
| Leer las dos colas y el estado de los dos negocios | sí, con clave de solo lectura |
| Cerrar tareas del cockpit | sí, con clave de escritura propia y recorte a `status` |
| Ejecutar las acciones del catálogo | sí, con contrato, vale de un solo uso, PIN y diario |
| Agenda | ver huecos y choques, crear, mover y cancelar citas |
| Correo de las dos cuentas | leer y dejar borradores. **Nunca envía** |
| Preguntarle cosas | sí, con Haiku, tope de 60 al día y el coste debajo de cada respuesta |
| Resumen de la mañana | sí, una vez al día, cacheado |
| Avisos al móvil | sí, Web Push, cinco al día como mucho |
| Dictar en buscar y en preguntar | sí, con el motor del navegador. Coste cero |
| Conversar por voz | sí, y ejecutar hablando **solo lo reversible** |
| Entrar con Face ID | sí, WebAuthn con la firma comprobada en el servidor |

**Lo que NO hace, y es a propósito:** enviar correo, publicar por voz, y decidir con un modelo qué
acción disparar (eso lo empareja `servicio/ordenes.py` con reglas).

## Las colas se abren enteras (28-sep)

La brecha era esta: 113 cosas esperaban el OK del operador y Zeno ponía delante **una**, porque
los feeds de aviso de los dos sistemas dan una cosa al día y el endpoint de colas devolvía el
recuento, no los elementos.

Cerrada del lado de **Zenvrax**: `GET /aios/cola/{cola}` entrega los elementos con sus acciones, y
en Zeno la ficha "44 Posts de X sin publicar" se toca y salen los 44. Son 82 de las 113.

**Lo que Zeno puede disparar ahí es solo lo reversible**, decidido por el operador: marcar
publicado, cancelar un magnet, descartar un thread. La lista vive en el cockpit
(`core/puerta_zeno.py`), ruta a ruta y con el cuerpo exacto, y es el cockpit quien marca cada
acción con si Zeno puede: replicar esa regla aquí serían dos listas que se separan. Lo que
publica no se ofrece como botón, lleva al cockpit.

**Cerrada tambien del lado de Xrise** (28-sep): las 31 de GutLyn y Claire se abren y se publican
desde el movil, porque el operador decidio que *"se pueda publicar puesto GutLyn es mia"*. Su
puerta vive en `saas/api/app/core/puerta_zeno.py`, con las acciones exactas (`publish`,
`regenerate`, `drop`) y no solo la ruta. Medido el 28-sep: las 8 colas responden las 113 enteras.

**Zeno** es el nombre que eligió el operador el 2026-09-27 entre cuatro. Sale de Zenvrax y se queda
en dos sílabas: la Z ata con la casa sin meterse en la línea X de los SaaS vendibles (Xrise, XSupport,
XGuiide), así que no se confunde con un producto ni con la consultora. Se descartó `Torre` porque ya
lo usa la torre de control de AIOS.

Nació en `lab/zeno/` y **graduó a este repo el 28-sep**, porque el operador decidió que **Zeno vive
fuera** del cockpit y de Xrise para mantenerlos independientes. Nada de producción depende de este
repo: la dependencia va al revés, esto **lee** el código de las dos aplicaciones.

---

## Qué hay aquí y para qué

El asistente va a ejecutar cosas en nombre del operador. Solo el cockpit tiene **190 rutas que
mutan**, y Xrise las suyas: si se le da esa API y se le pide que actúe, elige la llamada, y elegir es
adivinar. Así que la lista está cerrada: **41 acciones** (31 del cockpit, 10 de Xrise), las que ya son botones
en las dos colas de aprobación, cada una con su contrato. **28 escriben algo**; las otras 13 solo
abren una pantalla.

```
catalogo/
  recolector.py   lee del ARBOL de las dos colas: destino, verbo, cuerpo. No toca las aplicaciones
  contrato.py     el tipo `Contrato` y sus tres guardas (lo que publica no puede ser reversible…)
  metadatos.py    lo que el codigo NO dice, declarado una vez: si publica, si se deshace, si cuesta
  __init__.py     `catalogo()` une las dos mitades y FALLA si una accion no tiene contrato
ver_catalogo.py   para mirarlo: --ejecutan, --alcance, --json
tests/            10 pruebas, las cinco regresiones probadas con el fallo dentro
```

**Medido el 2026-09-27, revisado el 2026-10-07** (entra encargar el minado desde el movil):

| | cuántas | qué son |
|---|---|---|
| Sale al mundo | 8 | publican en LinkedIn, X, Meta o mandan correo. Irreversibles |
| Cambia estado | 20 | mueven algo dentro. 4 de ellas **gastan API de pago** |
| Solo abre | 13 | enlaces y vistas previas. No son acciones: no se confirman |

## El hallazgo que justifica la fase

**Tres acciones publican de verdad y están escritas exactamente igual que un enlace a una guía en
HTML.** Son webhooks de n8n por GET:

```python
{"url": f"{N8N_PUBLIC}/webhook/linkedin-approve?id={pid}", "label": "✅ Aprobar"}   # PUBLICA
{"url": "https://magnets.zenvrax.com/xsupport/alta/guia.html", "label": "Guía de envío"}  # abre
```

Nada en el dato las distingue. Un asistente que dedujera el efecto del verbo daría por hecho que un
GET no muta, y publicaría en LinkedIn creyendo que abre una pantalla. Por eso `efecto` se declara a
mano y el recolector se niega a inventarlo.

## Dos cosas que se descubrieron construyendo esto

1. **El verbo por omisión no es el mismo en las dos colas**, y se leyó de quien las ejecuta:
   `Notificaciones.tsx:228` del cockpit hace `a.patch.verb || "PATCH"`, y el de Xrise hace
   `api(a.call.path, "POST", ...)`, fijo. Suponer POST para las dos dio un falso negativo:
   `tema.marcar_publicado` no declara verbo y el endpoint real es `PATCH /marketing/topics/{id}`.
2. **Ocho de las acciones que mutan no tienen ninguna guarda.** No es un fallo que haya que tapar: es
   el dato que el asistente necesita para pedir confirmación. Un test fija el número en 8 para que no
   crezca sin que nadie se dé cuenta.

## J2 · Zeno leyendo (2026-09-27)

```
lector.py         cliente de las dos APIs. Solo GET, y un test lo comprueba del arbol
zeno.py           la consola: pendientes · estado · busca <texto> · todo
tests/test_lector.py
```

Entra con una clave de solo lectura por sistema (`X-Zeno-Key`), **distinta de la de n8n**, porque esa
abre endpoints que escriben. En Xrise manda además `X-Zeno-Org` y solo puede leer las organizaciones
de `ZENO_ORGS` (hoy `gutlyn`): Xrise se vende, y sin ese límite leería los datos de un cliente real.

**Lo que aporta sobre mirar las dos pantallas:** cruza cada aviso con el catálogo de J1, así que dice
si al aprobar algo **sale al mundo y no vuelve** o si **gasta una llamada de pago**, y pone lo
irreversible primero. Ninguna de las dos colas sabe eso.

**Tres cosas que no disimula:** un sistema que no contesta se dice en vez de devolver una lista corta;
una búsqueda degradada a texto se advierte; y una acción que el catálogo no reconoce se marca
SIN CONTRATO en vez de ocultarse.

## Cómo se ejecuta

```bash
python -m pytest tests -q                  # 375 pruebas en 17 ficheros
python ver_catalogo.py --ejecutan          # las 27 acciones que escriben algo
ZENO_READ_KEY=... python3 zeno.py todo     # lo pendiente y el estado, de los dos negocios
```

La clave vive en el `.env` del servidor. Sin ella, Zeno lo dice en vez de devolver listas vacías.

`.github/workflows/ci-zeno.yml` las corre cuando cambia una cola o el catálogo, porque el CI del
cockpit no las vería: corre `pytest` dentro de `cockpit/api`, cuyo `testpaths` es `tests`.

**Alcance, y conviene saberlo:** en CI solo está este repo, así que se validan las **30 acciones del
cockpit**. Las **10 de Xrise** viven en otro repo privado y el test las omite en vez de fallar;
`--alcance` lo dice. Se validan al correr los tests en local, donde los dos repos están en el disco.

## Lo que falta, medido contra producción el 2026-09-28

J3 (la puerta propia) y J4 (el correo y el calendario) están cerradas. Lo que queda, por orden de
lo que más le cuesta al operador:

**El correo se queda a un paso.** Zeno lee las dos bandejas y redacta el borrador, pero no envía:
hay que abrir Gmail para darle a enviar. Es la única tarea diaria que empieza en Zeno y termina
fuera.

**Solo cubre marketing y contacto.** Las 8 colas son contenido, DMs y engagement, más cerrar
tareas. Finanzas, leads, propuestas, facturas y solicitudes de acceso no tienen cola: sus alertas
sí llegan al móvil (el 28-sep sonaron el beneficio mensual y el runway), pero no hay nada que
hacer con ellas desde aquí.

**No busca al operador.** Fuera de los cinco avisos y las tres líneas de la mañana, Zeno es
reactivo: no dice "llevas tres días sin tocar los DMs" ni "esto lleva dos semanas esperando".
Tiene el dato y, desde el 28-sep, la memoria para no repetirlo.

**El resumen de la mañana es de una sola vez.** Se calcula al abrir la aplicación y queda cacheado
el día entero, así que a las seis de la tarde cuenta la mañana. Fue para no pagar diez llamadas
por abrirla diez veces; se puede rehacer cuando el pendiente cambie de verdad.

**Decidido NO hacer** (operador, 28-sep): que aprenda de lo que rechaza.

## Desplegar

```bash
# en el servidor
cd /home/zenvrax-zeno && git pull
docker compose -p zeno --env-file /home/zenvrax-io/.env \
    -f /home/zenvrax-zeno/infra/docker-compose.zeno.yml up -d --build
```

**Si tocas el Caddyfile, ojo con una trampa que costó media hora el 27-sep.** Caddy monta el
Caddyfile como FICHERO, por su inodo, y `git pull` lo reemplaza: el contenedor sigue leyendo el
viejo, y `caddy validate` y `caddy reload` **dan verde** sobre la configuración antigua. Hay que
escribir dentro del fichero montado:

```bash
docker exec -i zenvrax-io-caddy-1 sh -c 'cat > /etc/caddy/Caddyfile' \
    < /home/zenvrax-io/infrastructure/caddy/Caddyfile
docker exec zenvrax-io-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

Y comprobarlo, que es lo que lo caza en dos segundos:

```bash
diff <(cat /home/zenvrax-io/infrastructure/caddy/Caddyfile) \
     <(docker exec zenvrax-io-caddy-1 cat /etc/caddy/Caddyfile) && echo "el mismo"
```

## El DNS

`zeno.zenvrax.com` es un registro **A a 204.168.214.188 con el proxy de Cloudflare DESACTIVADO**,
igual que `xrise`, `aios` y `cockpit`. El comodín `*.zenvrax.com` apunta a Vercel con proxy, así que
sin registro propio el dominio daba **525** y Caddy no podía emitir el certificado.
