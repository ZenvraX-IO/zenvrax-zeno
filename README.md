# Zeno — el catálogo de acciones (J1)

**STATUS:** `experiment`
**Abierto:** 2026-09-27 · **Fase:** J1 del [plan del asistente](../../docs/PLAN-ASISTENTE.md)

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

## Cómo se ejecuta

```bash
python -m pytest lab/zeno/tests -q          # las 10 pruebas
python lab/zeno/ver_catalogo.py --ejecutan   # las 20 que escriben algo
```

`.github/workflows/ci-zeno.yml` las corre cuando cambia una cola o el catálogo, porque el CI del
cockpit no las vería: corre `pytest` dentro de `cockpit/api`, cuyo `testpaths` es `tests`.

**Alcance, y conviene saberlo:** en CI solo está este repo, así que se validan las **23 acciones del
cockpit**. Las **10 de Xrise** viven en otro repo privado y el test las omite en vez de fallar;
`--alcance` lo dice. Se validan al correr los tests en local, donde los dos repos están en el disco.

## Lo siguiente

J2: el asistente que solo LEE. No entra hasta que este catálogo esté cerrado, porque J2, J4 y J5
dependen de él.
