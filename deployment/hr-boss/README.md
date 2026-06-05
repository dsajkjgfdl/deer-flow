# HR Boss Docker Quickstart

This directory contains the HR Boss deployment overlay:

- `.env.example`: server-side variables and host paths.
- `extensions_config.docker.json`: MCP config using container paths.
- `Dockerfile.data-builder`: image for rebuilding MySQL, Neo4j and GraphRAG data from the Excel file.
- `rebuild_hr_kg.py`: containerized replacement for the local PowerShell rebuild script.

## Layout

Prepare these paths on the server:

```text
/opt/deer-flow                         # this repository
/opt/hr-mcp/text2cypher                # Text2Cypher repo, with Linux .venv
/opt/hr-mcp/graphrag-mcp               # GraphRAG MCP repo, with Linux .venv
/data/hr/source                        # 基本信息_filled_new.xlsx + import_compressed.py
/data/hr/graphrag/byog_graphrag        # BYOG GraphRAG project/data root
/data/deer-flow                        # DeerFlow runtime state
```

## Commands

Copy and edit env values:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
cp deployment/hr-boss/.env.example deployment/hr-boss/.env
cp deployment/hr-boss/extensions_config.docker.json extensions_config.hr-boss.json
```

Run from repository root:

```bash
set -a
. deployment/hr-boss/.env
set +a
```

`deployment/hr-boss/.env` should include `DEER_FLOW_REPO_ROOT=/opt/deer-flow` so Docker can map host-side skill paths correctly.

Rebuild data from Excel:

```bash
ls -la /data/hr/source

docker compose -p hr-boss \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.hr-boss.yaml \
  --profile rebuild run --build --rm hr-data-builder
```

Start runtime:

```bash
docker compose -p hr-boss \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.hr-boss.yaml \
  up -d --build nginx frontend gateway neo4j mysql
```

Open:

```text
http://SERVER_IP:2026
```

## Important

The rebuild job is destructive: it clears MySQL, clears Neo4j, removes generated GraphRAG folders, imports the Excel file, then runs BYOG `strict-sync-all`.

Do not run the rebuild job on every application restart. Run it only for first deployment or after replacing the source Excel file.

If the rebuild reports `Excel file does not exist`, check `HR_KG_SOURCE_DIR` and `HR_EXCEL_FILE` in `deployment/hr-boss/.env`. The host directory is mounted to `/app/hr-kg-source` inside the container.
