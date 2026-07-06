# HR Boss Docker Quickstart

This directory contains the HR Boss deployment overlay:

- `.env.example`: server-side variables and host paths.
- `offline.env.example`: server-side variables for the complete offline image bundle.
- `extensions_config.docker.json`: MCP config pointing Gateway at the independent HTTP MCP services.
- `Dockerfile.data-builder`: image for syncing Huoju HR APIs into MySQL, then rebuilding Neo4j and GraphRAG.
- `Dockerfile.data-builder.offline`: offline data-builder image that installs GraphRAG dependencies at build time.
- `sync_huoju_hr_data.py`: containerized Huoju API import, MySQL clean-layer rebuild, and BYOG sync entrypoint.
- `build-offline-bundle.ps1`: Windows build script for producing `hr-boss-images.tar` and `hr-boss-deploy-bundle.tgz`.
- `load-and-run.sh`: Linux server script for loading images and starting the offline runtime.

## Layout

Prepare these paths on the server:

```text
/opt/deer-flow                         # this repository
/opt/hr-mcp/text2cypher                # Text2Cypher repo, with Linux .venv
/opt/hr-mcp/graphrag-mcp               # GraphRAG MCP repo, with Linux .venv
/data/hr/apifox                        # 火炬hr.Apifox.json + 火炬token.Apifox.json
/data/hr/graphrag/byog_graphrag        # BYOG GraphRAG project/data root
/data/hr/logs/text2cypher              # writable Text2Cypher MCP logs
/data/deer-flow                        # DeerFlow runtime state
```

## Commands

Copy and edit env values:

```bash
mkdir -p /data/hr/logs/text2cypher

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

If the server cannot reach PyPI, npm, or Debian mirrors reliably, set build mirrors in `deployment/hr-boss/.env` before running `docker compose up --build`:

```dotenv
UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
NPM_REGISTRY=https://registry.npmmirror.com
# APT_MIRROR=mirrors.aliyun.com
```

The Gateway image uses `UV_INDEX_URL` during `uv sync`. If a build fails while fetching `hatchling` or another Python package from `https://pypi.org/simple`, this mirror setting is the first thing to check.

For WeCom/channel deployment, keep `GATEWAY_WORKERS=1`. Channel calls use a process-local internal auth token, so multiple Gateway workers can reject each other's internal LangGraph requests with 401.

The HR Boss compose overlay also loads `deployment/hr-boss/.env` into the Gateway container. After changing `WECOM_BOT_ID` or `WECOM_BOT_SECRET`, recreate the Gateway container so `config.yaml` can resolve the new `$WECOM_*` values from the container environment.

Prepare external MCP virtual environments on the server before starting the HTTP MCP services:

```bash
cd /opt/hr-mcp/text2cypher
test -f scripts/run_text2cypher_mcp.py || test -f text2cypher/adapters/mcp/server.py
rm -rf .venv
docker run --rm -v "$PWD":/work -w /work python:3.12-slim-bookworm \
  sh -lc 'python -m venv --copies .venv && . .venv/bin/activate && pip install -U pip && pip install -e .'
test -x .venv/bin/python

cd /opt/hr-mcp/graphrag-mcp
test -d src
rm -rf .venv
docker run --rm -v "$PWD":/work -w /work python:3.12-slim-bookworm \
  sh -lc 'python -m venv --copies .venv && . .venv/bin/activate && pip install -U pip && pip install -e .'
test -x .venv/bin/python
```

Do not rely on a host `uv sync` venv whose `.venv/bin/python` links to `/root/.local/share/uv/...`; that symlink can be valid on the host but broken inside the MCP service containers.

Sync and rebuild data from Huoju HR APIs:

```bash
ls -la /data/hr/apifox

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
  up -d --build nginx frontend gateway text2cypher-mcp hr-graphrag-mcp neo4j mysql
```

Open:

```text
http://SERVER_IP:2026
```

The MCP services are internal-only by default. Gateway connects to:

```text
http://text2cypher-mcp:8000/mcp
http://hr-graphrag-mcp:8000/mcp
```

Inspect their logs independently:

```bash
docker compose -p hr-boss -f docker/docker-compose.yaml -f docker/docker-compose.hr-boss.yaml logs -f text2cypher-mcp hr-graphrag-mcp
```

## Important

The rebuild job refreshes the Huoju MySQL raw tables, rebuilds the MySQL clean layer, clears Neo4j, removes generated GraphRAG folders, then runs BYOG `strict-sync-all`.

Do not run the rebuild job on every application restart. Run it only for first deployment or after the Huoju HR source data should be refreshed.

If the rebuild reports an Apifox file is missing, check `HUOJU_APIFOX_DIR`, `HUOJU_HR_APIFOX_FILE`, and `HUOJU_TOKEN_APIFOX_FILE` in `deployment/hr-boss/.env`. The host directory is mounted to `/data/hr/apifox` inside the container.

## Complete Offline Deployment

Use this mode when the target Linux amd64 server cannot access Docker registries,
PyPI, npm, or apt mirrors. Build everything on the Windows build machine, upload
two archives, then load and run them on the server.

Build on Windows from the DeerFlow repository:

```powershell
.\deployment\hr-boss\build-offline-bundle.ps1 `
  -HrMcpSuiteRoot D:\study\my-mcp\hr-mcp-suite
```

The script creates:

```text
dist/hr-boss-offline/hr-boss-images.tar
dist/hr-boss-offline/hr-boss-deploy-bundle.tgz
```

Upload both files to the server, then run:

```bash
mkdir -p /opt/hr-boss
tar -xzf hr-boss-deploy-bundle.tgz -C /opt/hr-boss
cp hr-boss-images.tar /opt/hr-boss/
cd /opt/hr-boss
bash load-and-run.sh hr-boss-images.tar
```

The first run creates `deployment/hr-boss/.env` and
`deployment/hr-boss/config.hr-boss.yaml`, then exits so you can edit secrets and
paths. Replace every `replace_with_*` value and rerun the same command.

The offline Compose file is standalone and contains no `build:` sections:

```bash
docker compose --env-file deployment/hr-boss/.env -p hr-boss \
  -f docker/docker-compose.hr-boss.offline.yaml ps
```

The runtime start does not rebuild HR data automatically. Run the destructive
rebuild only for first deployment or when the Huoju HR source data should be refreshed:

```bash
docker compose --env-file deployment/hr-boss/.env -p hr-boss \
  -f docker/docker-compose.hr-boss.offline.yaml \
  --profile rebuild run --rm hr-data-builder
```
