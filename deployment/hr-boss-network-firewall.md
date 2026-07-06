# HR Boss 内网部署网络与防火墙清单

本文面向在公司内网堡垒机部署 HR Boss 的运维人员，覆盖当前生产配置实际启用的 DeerFlow、Text2Cypher、GraphRAG、飞书和企业微信能力。

本文不包含当前未启用的网页搜索、其他模型平台、LangSmith/Langfuse、其他 IM 渠道和 Kubernetes Sandbox。

## 1. 放行原则

- 外部服务使用动态 IP 和 CDN，防火墙应按 FQDN 放行，不应维护固定公网 IP。
- 外部访问原则上只开放 `TCP/443`。仅 Debian/APT 镜像可能使用 `TCP/80`。
- 业务用户只需要访问堡垒机的 `TCP/2027`。
- MySQL、Neo4j、Gateway、Frontend 和 MCP 端口不应对公司网络开放。
- Docker 构建和容器运行流量经过 Docker bridge/NAT。防火墙规则必须同时允许 Docker 容器出站，不能只允许宿主机进程出站。
- 飞书和企业微信均由 Gateway 主动建立 WebSocket 长连接，不需要公网入站回调端口。

## 2. 最小长期开放清单

以下规则用于系统正常运行，应长期允许堡垒机及其 Docker 容器出站。

| 方向 | 来源 | 目标 FQDN | 协议/端口 | 用途 | 必要性 |
| --- | --- | --- | --- | --- | --- |
| 出站 | `gateway`、`text2cypher-mcp` | `api.deepseek.com` | HTTPS `TCP/443` | DeerFlow 主模型和 Text2Cypher 模型调用 | 必须 |
| 出站 | `hr-graphrag-mcp`、`hr-data-builder` | `dashscope.aliyuncs.com` | HTTPS `TCP/443` | GraphRAG 查询、Embedding 和数据重建 | 必须 |
| 出站 | `gateway` | `open.feishu.cn` | HTTPS `TCP/443` | 飞书 API 调用和获取 WebSocket 地址 | 当前启用 |
| 出站 | `gateway` | `*.feishu.cn` | WSS/HTTPS `TCP/443` | 飞书动态返回的长连接地址，例如 `msg-frontier-*.feishu.cn` | 当前启用 |
| 出站 | `gateway` | `openws.work.weixin.qq.com` | WSS `TCP/443` | 企业微信智能机器人长连接 | 当前启用 |
| 出站 | `gateway` | `wework.qpic.cn` | HTTPS `TCP/443` | 下载企业微信消息中的图片和文件 | 使用企微附件时必须 |
| 出站 | `gateway` | `wwcdn.weixin.qq.com` | HTTPS `TCP/443` | 下载企业微信消息中的图片和文件 | 使用企微附件时必须 |
| 出站 | `gateway` | `rescdn.qqmail.com` | HTTPS `TCP/443` | 企业微信文件资源 CDN | 使用企微附件时建议 |
| 出站 | 宿主机和所有容器 | 公司内部 DNS | DNS `UDP/53`、`TCP/53` | 解析外部 FQDN 和 Docker 外部目标 | 必须 |
| 出站 | 宿主机 | 公司内部 NTP | NTP `UDP/123` | 保持 TLS、Token 和日志时间正确 | 强烈建议 |

### 飞书动态域名说明

飞书 SDK 首先访问：

```text
https://open.feishu.cn/callback/ws/endpoint
```

接口会动态返回 WebSocket 地址。当前防火墙建议允许 `*.feishu.cn:443`。如果公司不允许通配符，可在 Gateway 日志中记录实际返回的 `wss://` 主机名，再逐个加入白名单；每次 SDK 或平台升级后需要重新核对。

### 企业微信附件域名说明

企业微信文本消息只依赖 `openws.work.weixin.qq.com:443`。图片和文件消息中的下载 URL 由企业微信动态下发，除表中域名外仍可能出现新的腾讯 CDN FQDN。若防火墙严格限制域名，应在联调期间记录实际附件 URL 的主机名并追加白名单。

## 3. 首次部署和构建期开放清单

以下规则用于拉取镜像、构建 Gateway/Frontend、创建 MCP 虚拟环境和重建 HR 数据。建议仅在发布窗口开放，构建完成后关闭。

### 3.1 Docker Hub

当前部署会从 Docker Hub 拉取以下镜像：

```text
nginx:alpine
node:22-alpine
python:3.12-slim-bookworm
docker:cli
mysql:8.4
neo4j:5
```

| 目标 FQDN | 协议/端口 | 用途 |
| --- | --- | --- |
| `auth.docker.io` | HTTPS `TCP/443` | Docker Hub Token 鉴权 |
| `registry-1.docker.io` | HTTPS `TCP/443` | 镜像 Manifest 和 Layer 拉取 |
| `production.cloudfront.docker.com` | HTTPS `TCP/443` | Docker Hub 镜像 Layer CDN |

Docker Hub 可能调整或增加重定向 CDN。若 `docker pull` 已通过鉴权但 Layer 下载失败，应根据 Docker daemon 日志补充实际重定向 FQDN。

### 3.2 GitHub Container Registry

Gateway 构建默认从以下地址拉取 `uv`：

```text
ghcr.io/astral-sh/uv:0.7.20
```

| 目标 FQDN | 协议/端口 | 用途 |
| --- | --- | --- |
| `ghcr.io` | HTTPS `TCP/443` | GitHub Container Registry |
| `pkg-containers.githubusercontent.com` | HTTPS `TCP/443` | GHCR 镜像 Layer 下载 |
| `*.pkg.github.com` | HTTPS `TCP/443` | GitHub Packages 相关重定向 |

### 3.3 Python 包仓库

当前 HR Boss 示例配置使用阿里云 Python 镜像：

```dotenv
UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

| 目标 FQDN | 协议/端口 | 用途 | 说明 |
| --- | --- | --- | --- |
| `mirrors.aliyun.com` | HTTPS `TCP/443` | Gateway、MCP 和 Python 依赖下载 | 推荐主要路径 |
| `pypi.org` | HTTPS `TCP/443` | Python 官方索引 | 未使用镜像或镜像失败时需要 |
| `files.pythonhosted.org` | HTTPS `TCP/443` | Python 官方包文件下载 | 未使用镜像或镜像重定向时需要 |

注意：

- Gateway 构建使用 `UV_INDEX_URL`。
- 外部 MCP `.venv` 初始化脚本使用 `PIP_INDEX_URL`。
- `hr-data-builder` 镜像构建和运行期执行 `pip install -e` 时可能访问 Python 包仓库。
- 如果运维要求只开放阿里云镜像，必须先验证所有构建步骤均不会回退到 `pypi.org` 或 `files.pythonhosted.org`。

### 3.4 npm/pnpm 包仓库

当前 Frontend 构建使用：

```dotenv
NPM_REGISTRY=https://registry.npmmirror.com
```

| 目标 FQDN | 协议/端口 | 用途 |
| --- | --- | --- |
| `registry.npmmirror.com` | HTTPS `TCP/443` | 下载 pnpm 和 Frontend npm 依赖 |

若镜像返回其他 CDN 下载地址，应按实际重定向 FQDN追加白名单。

### 3.5 Debian/APT

Gateway 和数据构建镜像会执行 `apt-get`。Gateway 的 Node.js 运行时来自可覆盖的 `BACKEND_NODE_IMAGE` 构建阶段，不再访问 NodeSource。

| 目标 FQDN | 协议/端口 | 用途 | 使用条件 |
| --- | --- | --- | --- |
| `deb.debian.org` | HTTP `TCP/80` | Debian 软件包和安全更新 | 未设置 `APT_MIRROR` 时 |
| `mirrors.aliyun.com` | HTTP `TCP/80`、HTTPS `TCP/443` | Debian 阿里云镜像 | 设置 `APT_MIRROR=mirrors.aliyun.com` 时 |

建议在 `deployment/hr-boss/.env` 中设置：

```dotenv
APT_MIRROR=mirrors.aliyun.com
```

### 3.6 Neo4j APOC 插件

当前 Neo4j 配置包含：

```yaml
NEO4J_PLUGINS: '["apoc"]'
```

Neo4j 首次启动、插件缺失或版本变化时可能从 GitHub Release 下载 APOC。发布窗口应同时开放第 4 节中的 GitHub 域名。插件下载完成后，应确认插件已持久化到 `hr-boss-neo4j-plugins` volume。

## 4. 代码更新期开放清单

DeerFlow 和 `hr-mcp-suite` 当前均通过 GitHub HTTPS remote 更新，不需要开放 Git SSH `TCP/22`。

| 目标 FQDN | 协议/端口 | 用途 |
| --- | --- | --- |
| `github.com` | HTTPS `TCP/443` | `git clone`、`git pull`、Release 页面和 Neo4j APOC 下载 |
| `*.githubusercontent.com` | HTTPS `TCP/443` | GitHub Raw、Release 资源和对象下载 |
| `release-assets.githubusercontent.com` | HTTPS `TCP/443` | GitHub Release 文件下载 |
| `objects.githubusercontent.com` | HTTPS `TCP/443` | GitHub 对象下载 |

当前两个仓库没有提交 Git LFS 文件。若以后启用 Git LFS，需要根据 GitHub 返回的 LFS 存储域名追加白名单。

## 5. 堡垒机入站端口

| 端口 | 来源网段 | 用途 | 策略 |
| --- | --- | --- | --- |
| `TCP/2027` | 公司业务访问网段或上游负载均衡 | DeerFlow 统一 Web/API 入口 | 允许 |
| `TCP/22` | 运维管理网段 | 堡垒机 SSH 管理 | 由公司运维策略控制，非应用必需 |
| `TCP/3306` | 无 | MySQL 调试端口 | 禁止对公司网络开放 |
| `TCP/7474` | 无 | Neo4j HTTP 调试端口 | 禁止对公司网络开放 |
| `TCP/7687` | 无 | Neo4j Bolt 调试端口 | 禁止对公司网络开放 |

`docker/docker-compose.hr-boss.yaml` 当前会把 `3306`、`7474` 和 `7687` 发布到宿主机。即使保留端口映射，也必须通过宿主机防火墙限制为本机或指定管理网段。更严格的生产部署应删除这些 `ports`，或绑定到 `127.0.0.1`。

`2026` 当前提供的是 HTTP 服务。如果公司要求 HTTPS，应由上游负载均衡或公司反向代理监听 `TCP/443` 并转发到堡垒机 `TCP/2026`，不要直接把数据库或 Gateway 端口暴露给上游。

例如仅绑定本机：

```dotenv
MYSQL_PUBLISHED_PORT=127.0.0.1:3306
NEO4J_HTTP_PUBLISHED_PORT=127.0.0.1:7474
NEO4J_BOLT_PUBLISHED_PORT=127.0.0.1:7687
```

Compose 展开后会分别得到 `127.0.0.1:3306:3306`、`127.0.0.1:7474:7474` 和 `127.0.0.1:7687:7687`。

Linux Docker 会创建自己的防火墙和 NAT 规则，已发布的容器端口不一定符合简单 UFW 规则的预期。建议同时采用“数据库端口绑定回环地址 + 堡垒机外围防火墙限制”的方式；如必须发布到非回环网卡，再由运维在 Docker `DOCKER-USER` 链实施来源地址控制。

## 6. Docker 内部通信端口

以下端口仅在 Docker `deer-flow` bridge 网络内使用，不需要在公司边界防火墙开放。

| 来源服务 | 目标服务 | 端口 | 用途 |
| --- | --- | --- | --- |
| `nginx` | `frontend` | `TCP/3000` | Web 前端 |
| `nginx` | `gateway` | `TCP/8001` | Gateway API |
| `gateway` | `gateway` | `TCP/8001` | 内部 Channel/LangGraph 调用 |
| `gateway` | `text2cypher-mcp` | `TCP/8000` | Text2Cypher HTTP MCP |
| `gateway` | `hr-graphrag-mcp` | `TCP/8000` | GraphRAG HTTP MCP |
| `text2cypher-mcp`、`hr-data-builder` | `neo4j` | `TCP/7687` | Neo4j Bolt |
| `hr-data-builder` | `neo4j` | `TCP/7474` | Neo4j 健康检查 |
| `hr-data-builder` | `mysql` | `TCP/3306` | HR 数据导入 |
| 宿主机 | `nginx` | `TCP/2026` | 统一入口端口映射 |

不要为 `3000`、`8000` 或 `8001` 增加宿主机 `ports` 映射。

## 7. 推荐的运维放行策略

### 7.1 长期开放

```text
api.deepseek.com:443
dashscope.aliyuncs.com:443
open.feishu.cn:443
*.feishu.cn:443
openws.work.weixin.qq.com:443
wework.qpic.cn:443
wwcdn.weixin.qq.com:443
rescdn.qqmail.com:443
公司内部 DNS:53/UDP,TCP
公司内部 NTP:123/UDP
```

### 7.2 仅部署、构建和更新窗口开放

```text
auth.docker.io:443
registry-1.docker.io:443
production.cloudfront.docker.com:443
ghcr.io:443
pkg-containers.githubusercontent.com:443
*.pkg.github.com:443
mirrors.aliyun.com:80,443
pypi.org:443
files.pythonhosted.org:443
registry.npmmirror.com:443
deb.debian.org:80
github.com:443
*.githubusercontent.com:443
release-assets.githubusercontent.com:443
objects.githubusercontent.com:443
```

### 7.3 入站开放

```text
业务访问网段 -> 堡垒机:2027/TCP
运维管理网段 -> 堡垒机:22/TCP
```

### 7.4 明确禁止

```text
公司网络 -> 堡垒机:3000/TCP
公司网络 -> 堡垒机:8000/TCP
公司网络 -> 堡垒机:8001/TCP
公司网络 -> 堡垒机:3306/TCP
公司网络 -> 堡垒机:7474/TCP
公司网络 -> 堡垒机:7687/TCP
```

## 8. 代理和 TLS 检查注意事项

- Docker 镜像拉取由 Docker daemon 发起。只给当前 Shell 设置 `HTTPS_PROXY` 不足以让 `docker pull` 走代理，需要配置 Docker daemon 代理。
- Docker build 内的 `apt`、`uv`、`pip`、`pnpm` 流量来自构建容器，需要允许 Docker bridge/NAT 出站。
- GraphRAG `settings.yaml` 当前为模型连接设置了 `trust_env: false`，不会自动使用容器中的 `HTTP_PROXY`/`HTTPS_PROXY`。优先配置直接 FQDN 出站或透明代理。
- 飞书和企业微信使用 WebSocket over TLS。代理和防火墙必须支持 `HTTP Upgrade` 和长时间连接，不能按普通短连接超时主动断开。
- 若公司使用 TLS 解密代理，需将公司根证书安装到宿主机、Docker daemon、构建镜像和运行容器的 CA 信任库。模型 SDK、Python `certifi` 和 WebSocket SDK可能不会自动读取系统代理证书。
- 不要记录或向运维工单粘贴 `DASHSCOPE_API_KEY`、`ALIBABA_API_KEY`、`FEISHU_APP_SECRET`、`WECOM_BOT_SECRET` 等密钥。

## 9. 运维验证命令

以下命令应在堡垒机上执行。HTTP 返回 `401`、`403`、`404` 或 `405` 仍可证明 DNS、TCP 和 TLS 已连通；连接超时、拒绝或证书错误才表示网络未配置完成。

### 9.1 DNS 和 TLS

```bash
for host in \
  api.deepseek.com \
  dashscope.aliyuncs.com \
  open.feishu.cn \
  openws.work.weixin.qq.com \
  auth.docker.io \
  registry-1.docker.io \
  production.cloudfront.docker.com \
  ghcr.io \
  mirrors.aliyun.com \
  registry.npmmirror.com \
  github.com
do
  echo "===== $host ====="
  getent hosts "$host"
  timeout 10 openssl s_client -connect "$host:443" -servername "$host" </dev/null 2>/dev/null |
    grep -E "subject=|issuer=|Verify return code"
done
```

### 9.2 HTTP 服务连通性

```bash
curl -sS -o /dev/null -w 'DeepSeek: %{http_code}\n' https://api.deepseek.com/models
curl -sS -o /dev/null -w 'DashScope: %{http_code}\n' https://dashscope.aliyuncs.com/compatible-mode/v1/models
curl -sS -o /dev/null -w 'Feishu: %{http_code}\n' https://open.feishu.cn
curl -sS -o /dev/null -w 'Aliyun PyPI: %{http_code}\n' https://mirrors.aliyun.com/pypi/simple/hatchling/
curl -sS -o /dev/null -w 'npm mirror: %{http_code}\n' https://registry.npmmirror.com/pnpm
curl -sS -o /dev/null -w 'GitHub: %{http_code}\n' https://github.com
```

### 9.3 镜像拉取

```bash
docker pull nginx:alpine
docker pull node:22-alpine
docker pull python:3.12-slim-bookworm
docker pull docker:cli
docker pull mysql:8.4
docker pull neo4j:5
docker pull ghcr.io/astral-sh/uv:0.7.20
```

### 9.4 Compose 最终配置和监听端口

```bash
cd /opt/deer-flow
set -a
. deployment/hr-boss/.env
set +a

docker compose -p hr-boss \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.hr-boss.yaml \
  config > /tmp/hr-boss-compose.resolved.yaml

docker compose -p hr-boss \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.hr-boss.yaml \
  ps

ss -lntp | grep -E ':(22|2026|3000|3306|7474|7687|8000|8001)\b'
```

预期：

- `2026` 对业务访问网段可达。
- `3306`、`7474`、`7687` 即使处于监听状态，也被宿主机防火墙阻止从公司网络访问。
- `3000`、`8000`、`8001` 不应出现在宿主机对外监听列表。

### 9.5 Docker 内部通信

```bash
docker exec -i deer-flow-gateway python - <<'PY'
import socket

targets = [
    ("text2cypher-mcp", 8000),
    ("hr-graphrag-mcp", 8000),
    ("neo4j", 7687),
    ("mysql", 3306),
]
for host, port in targets:
    try:
        with socket.create_connection((host, port), timeout=5):
            print(f"OK   {host}:{port}")
    except Exception as exc:
        print(f"FAIL {host}:{port} {exc}")
PY
```

### 9.6 应用健康和渠道日志

```bash
curl -f http://127.0.0.1:2026/health
curl -s http://127.0.0.1:2026/api/mcp/config

docker compose -p hr-boss \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.hr-boss.yaml \
  logs --tail=200 gateway text2cypher-mcp hr-graphrag-mcp neo4j |
  grep -Ei 'connected|websocket|feishu|wecom|mcp|error|timeout|refused|certificate'
```

## 10. 部署前运维检查表

- [ ] 支持按 FQDN 配置出站白名单。
- [ ] Docker 宿主机和 Docker bridge/NAT 流量均可命中出站规则。
- [ ] 已长期开放第 2 节运行期域名。
- [ ] 已在发布窗口开放第 3、4 节构建和更新域名。
- [ ] `docker pull` 七个验证镜像全部成功。
- [ ] DeepSeek、DashScope、飞书和企业微信 TLS 连通。
- [ ] 代理支持 WebSocket Upgrade 和长连接。
- [ ] 业务网段可以访问 `TCP/2026`。
- [ ] 公司网络无法访问 `3306`、`7474`、`7687`。
- [ ] 公司网络无法直接访问 `3000`、`8000`、`8001`。
- [ ] Docker 内部服务名和端口通信正常。
- [ ] Gateway 日志中没有 DNS、连接拒绝、超时或证书错误。
- [ ] 发布完成后已关闭仅部署/构建期的外部白名单。

## 11. 后续收敛建议

长期建议将 Docker 镜像、Python 包、npm 包和 GitHub Release 制品同步到公司内部制品仓库。完成后，部署构建期只需要访问内部仓库；公网长期白名单可收敛为 DeepSeek、DashScope、飞书和企业微信。

参考：

- Docker Hub 官方网络白名单：<https://docs.docker.com/desktop/setup/allow-list/>
- Docker 防火墙和数据包过滤：<https://docs.docker.com/engine/network/packet-filtering-firewalls/>
- Docker daemon 代理配置：<https://docs.docker.com/engine/daemon/proxy/>
- GitHub 外部网络域名说明：<https://docs.github.com/en/actions/reference/runners/self-hosted-runners>
- DeepSeek API Base URL：<https://api-docs.deepseek.com/>
- 阿里云百炼 OpenAI 兼容接口：<https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope>
- 飞书长连接接收事件：<https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case>
- 企业微信域名列表：<https://res.mail.qq.com/zh_CN/wework_ip/latest.html>
