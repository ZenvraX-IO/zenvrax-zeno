# Comprobar Zeno en un navegador de verdad

Lo que el CSS y los tests no pueden decir: si la pantalla se usa y si la conversacion avanza.
Se ejecutan contra **produccion**, con un token emitido en el servidor en vez de la contraseña:
lo que se verifica es la pantalla, no el login.

El token se emite asi, en el servidor:

    docker exec -w /app zeno-api python -c "from servicio import clave; print(clave.emite('<tu correo>'))"

Y luego, en local:

    python comprobar/mira_conversa.py "<el token>" /ruta/donde/dejar/las/fotos

## Que hay

- `mira_voz.py` los dos botones de dictar: que salgan, escuchen y paren.
- `mira_conversa.py` la conversacion entera. Sustituye el microfono y el altavoz por unos de
  mentira (no se pueden fingir de otra forma) y deja el resto del codigo real: la puerta de
  ordenes, la confirmacion hablada y la ejecucion.

## Dos reglas al usarlos

**El paso que gasta va apagado.** Preguntarle algo al chat es una llamada a Haiku; los demas
pasos van por `/api/orden`, que empareja con reglas y cuesta cero. Ese paso solo corre si la
variable de entorno de permiso de gasto viene puesta a 1, y eso lo autoriza el operador con la
cifra delante, no quien ejecuta el guion.

**Las pruebas que tocan datos se hacen sobre una tarea creada para eso y se borran al acabar.**
Nunca sobre una tarea real: marcar hecha algo que no lo esta es falsear el estado del negocio.
