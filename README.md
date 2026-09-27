# Zeno — el asistente (J1 y J2)

**STATUS:** `experiment`
**Abierto:** 2026-09-27 · **Fases cerradas:** J1 (catálogo) y J2 (Zeno leyendo) del
[plan del asistente](../../docs/PLAN-ASISTENTE.md)

**Zeno** es el nombre que eligió el operador el 2026-09-27 entre cuatro. Sale de Zenvrax y se queda
en dos sílabas: la Z ata con la casa sin meterse en la línea X de los SaaS vendibles (Xrise, XSupport,
XGuiide), así que no se confunde con un producto ni con la consultora. Se descartó `Torre` porque ya
lo usa la torre de control de AIOS.

Vive en `lab/` porque es un proyecto nuevo y la regla del repo lo pide. Cuando gradúe será el repo
hermano `zenvrax-zeno/`, porque el operador decidió que **Zeno vive fuera** del cockpit y de Xrise
para mantenerlos independientes. Nada de producción depende de esta carpeta: la dependencia
va al revés, esto **lee** el código de las dos aplicaciones.

---

## Qué hay aquí y para qué

El asistente va a ejecutar cosas en nombre del operador. Solo el cockpit tiene **190 rutas que
mutan**, y Xrise las suyas: si se le da esa API y se le pide que actúe, elige la llamada, y elegir es
adivinar. Así que la lista está cerrada: **33 acciones**, las que ya son botones en las dos colas de
aprobación, cada una con su contrato.

```
catalogo/
  recolector.py   lee del ARBOL de las dos colas: destino, verbo, cuerpo. No toca las aplicaciones
  contrato.py     el tipo `Contrato` y sus tres guardas (lo que publica no puede ser reversible…)
  metadatos.py    lo que el codigo NO dice, declarado una vez: si publica, si se deshace, si cuesta
  __init__.py     `catalogo()` une las dos mitades y FALLA si una accion no tiene contrato
ver_catalogo.py   para mirarlo: --ejecutan, --alcance, --json
tests/            10 pruebas, las cinco regresiones probadas con el fallo dentro
```

**Medido el 2026-09-27:**

| | cuántas | qué son |
|---|---|---|
| Sale al mundo | 8 | publican en LinkedIn, X, Meta o mandan correo. Irreversibles |
| Cambia estado | 12 | mueven algo dentro. 3 de ellas **gastan API de pago** |
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
python -m pytest lab/zeno/tests -q               # 17 pruebas (10 del catalogo, 7 del lector)
python lab/zeno/ver_catalogo.py --ejecutan        # las 20 acciones que escriben algo
ZENO_READ_KEY=... python3 lab/zeno/zeno.py todo   # lo pendiente y el estado, de los dos negocios
```

La clave vive en el `.env` del servidor. Sin ella, Zeno lo dice en vez de devolver listas vacías.

`.github/workflows/ci-zeno.yml` las corre cuando cambia una cola o el catálogo, porque el CI del
cockpit no las vería: corre `pytest` dentro de `cockpit/api`, cuyo `testpaths` es `tests`.

**Alcance, y conviene saberlo:** en CI solo está este repo, así que se validan las **23 acciones del
cockpit**. Las **10 de Xrise** viven en otro repo privado y el test las omite en vez de fallar;
`--alcance` lo dice. Se validan al correr los tests en local, donde los dos repos están en el disco.

## Lo siguiente

**J3: la puerta propia** (`zeno.zenvrax.com`), que es cuando la app se vuelve necesaria. Queda
pendiente el icono, que lo elige el operador.

**J4: el correo y el calendario.** Hoy Zeno lee los dos sistemas, no la bandeja. Serán **dos
autorizaciones OAuth separadas**, una por cuenta de Google, porque las cuentas del operador ya están
separadas por negocio: así la frontera la sostiene Google y no un `if` en el código.
