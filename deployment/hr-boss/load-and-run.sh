#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="deployment/hr-boss/.env"
ENV_EXAMPLE="deployment/hr-boss/offline.env.example"
CONFIG_FILE="deployment/hr-boss/config.hr-boss.yaml"
CONFIG_EXAMPLE="deployment/hr-boss/config.hr-boss.example.yaml"
COMPOSE_FILE="docker/docker-compose.hr-boss.offline.yaml"

if [ ! -f "$ENV_FILE" ]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  if [ ! -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
  fi
  cat <<EOF
Created $ENV_FILE and $CONFIG_FILE.

Edit $ENV_FILE first:
  - replace BETTER_AUTH_SECRET and all replace_with_* values
  - confirm /opt/hr-boss paths match this deploy directory
  - confirm /data/hr/apifox contains the Huoju HR and token Apifox exports

Then rerun:
  bash load-and-run.sh /path/to/hr-boss-images.tar
EOF
  exit 1
fi

if grep -Eq "replace_with|change-me" "$ENV_FILE"; then
  echo "Refusing to start: $ENV_FILE still contains placeholder values." >&2
  grep -En "replace_with|change-me" "$ENV_FILE" >&2 || true
  exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
  cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${COMPOSE_PROJECT_NAME:=hr-boss}"
: "${DEER_FLOW_HOME:?set DEER_FLOW_HOME in $ENV_FILE}"
: "${DEER_FLOW_CONFIG_PATH:?set DEER_FLOW_CONFIG_PATH in $ENV_FILE}"
: "${DEER_FLOW_EXTENSIONS_CONFIG_PATH:?set DEER_FLOW_EXTENSIONS_CONFIG_PATH in $ENV_FILE}"
: "${HUOJU_APIFOX_DIR:?set HUOJU_APIFOX_DIR in $ENV_FILE}"
: "${BYOG_GRAPHRAG_ROOT:?set BYOG_GRAPHRAG_ROOT in $ENV_FILE}"
: "${HR_TEXT2CYPHER_LOG_DIR:=/data/hr/logs/text2cypher}"

mkdir -p "$DEER_FLOW_HOME" "$HUOJU_APIFOX_DIR" "$BYOG_GRAPHRAG_ROOT" "$HR_TEXT2CYPHER_LOG_DIR"

if [ ! -f "$DEER_FLOW_CONFIG_PATH" ]; then
  mkdir -p "$(dirname "$DEER_FLOW_CONFIG_PATH")"
  cp "$CONFIG_EXAMPLE" "$DEER_FLOW_CONFIG_PATH"
fi

if [ ! -f "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
  mkdir -p "$(dirname "$DEER_FLOW_EXTENSIONS_CONFIG_PATH")"
  cp "deployment/hr-boss/extensions_config.docker.json" "$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp ".env.example" ".env"
fi

if [ ! -f "frontend/.env" ] && [ -f "frontend/.env.example" ]; then
  cp "frontend/.env.example" "frontend/.env"
fi

SEED_GRAPHRAG_ROOT="$SCRIPT_DIR/hr-mcp-suite/data/byog_graphrag"
if [ -d "$SEED_GRAPHRAG_ROOT" ] && [ ! -f "$BYOG_GRAPHRAG_ROOT/settings.yaml" ]; then
  echo "Seeding GraphRAG project files into $BYOG_GRAPHRAG_ROOT"
  cp -a "$SEED_GRAPHRAG_ROOT"/. "$BYOG_GRAPHRAG_ROOT"/
fi

IMAGE_TAR="${1:-$SCRIPT_DIR/hr-boss-images.tar}"
if [ "${1:-}" = "--skip-load" ]; then
  IMAGE_TAR=""
fi

if [ -n "$IMAGE_TAR" ]; then
  if [ ! -f "$IMAGE_TAR" ]; then
    echo "Image archive not found: $IMAGE_TAR" >&2
    echo "Pass --skip-load only if all images are already loaded." >&2
    exit 1
  fi
  docker load -i "$IMAGE_TAR"
fi

if [ ! -f "$HUOJU_APIFOX_DIR/${HUOJU_HR_APIFOX_FILE:-火炬hr.Apifox.json}" ] || \
   [ ! -f "$HUOJU_APIFOX_DIR/${HUOJU_TOKEN_APIFOX_FILE:-火炬token.Apifox.json}" ]; then
  echo "Warning: Huoju Apifox exports are not present under $HUOJU_APIFOX_DIR." >&2
  echo "The runtime can start, but hr-data-builder will fail until Apifox files are copied." >&2
fi

docker compose --env-file "$ENV_FILE" -p "$COMPOSE_PROJECT_NAME" \
  -f "$COMPOSE_FILE" \
  up -d nginx frontend gateway text2cypher-mcp hr-graphrag-mcp neo4j mysql

cat <<EOF

HR Boss runtime started.

Open:
  http://SERVER_IP:${PORT:-2026}

Optional first-time or source-data refresh command:
  docker compose --env-file $ENV_FILE -p $COMPOSE_PROJECT_NAME \\
    -f $COMPOSE_FILE --profile rebuild run --rm hr-data-builder

Inspect services:
  docker compose --env-file $ENV_FILE -p $COMPOSE_PROJECT_NAME \\
    -f $COMPOSE_FILE ps
EOF
