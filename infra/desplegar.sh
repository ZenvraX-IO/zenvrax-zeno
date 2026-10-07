#!/usr/bin/env bash
# Despliega Zeno. SIEMPRE con este guion, nunca con `docker compose` a mano.
#
# POR QUE EXISTE (2026-10-07). Se recreo el contenedor con `docker compose up -d --build` desde
# /home/zenvrax-zeno/infra y Zeno se quedo SIN NINGUNA clave: el compose las toma de `${...}` y el
# .env no esta aqui, esta en /home/zenvrax-io/.env. El contenedor arranco, el healthcheck dijo
# `healthy` porque /api/salud no mira las claves, y la aplicacion del movil se lleno de
# "SinClave en /autopilot/plan". Es el mismo fallo que ya tenia escrito Xrise, que se despliega
# igual (-p xrise y el env de zenvrax-io); tenerlo escrito no basto, asi que ahora esta aqui.
#
# Dos cosas que este guion hace y el comando a mano no:
#   1. fija el proyecto (-p zeno) y el fichero de entorno, que es el de zenvrax-io
#   2. COMPRUEBA las claves despues de levantar, y falla en rojo si alguna se quedo vacia
set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/zenvrax-io/.env}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$AQUI/docker-compose.zeno.yml"

[ -f "$ENV_FILE" ] || { echo "FALTA el fichero de entorno: $ENV_FILE"; exit 1; }

echo "▸ desplegando Zeno (-p zeno, env $ENV_FILE)"
docker compose -p zeno --env-file "$ENV_FILE" -f "$COMPOSE" up -d --build

echo "▸ esperando a que responda"
for i in $(seq 1 30); do
  estado="$(docker inspect zeno-api --format '{{.State.Health.Status}}' 2>/dev/null || echo '?')"
  [ "$estado" = "healthy" ] && break
  sleep 2
done
echo "  estado: ${estado:-?}"

# Las que, vacias, dejan a Zeno funcionando A MEDIAS sin que nada lo grite: la de lectura lo deja
# ciego (es la que fallo), la de escritura hace que aprobar devuelva 401, la del cofre le impide
# guardar el permiso de Google, y sin la de Anthropic el chat no contesta.
echo "▸ claves dentro del contenedor"
falta=0
for v in ZENO_READ_KEY ZENO_WRITE_KEY ZENO_COFRE_KEY ANTHROPIC_API_KEY ZENO_VAPID_PRIVADA ZENO_CLAVE_HASH ZENO_PIN_HASH; do
  # Se mira si TIENE valor, nunca cual: esto se ejecuta en una terminal y queda en el historial.
  if docker exec zeno-api sh -c "[ -n \"\${$v:-}\" ]" 2>/dev/null; then
    echo "  ok   $v"
  else
    echo "  MAL  $v vacia"
    falta=$((falta + 1))
  fi
done

if [ "$falta" -gt 0 ]; then
  echo
  echo "⚠ $falta clave(s) vacias: Zeno arranca pero trabaja a medias y lo dira como 'SinClave'."
  echo "  Mira que esten en $ENV_FILE y vuelve a lanzar esto."
  exit 1
fi

echo
echo "deploy OK"
