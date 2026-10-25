# 为什么 Job-RAG 的 MCP 能远程访问，又不直接暴露数据库？

> 本文说明**当前这台服务器**的访问链路与操作方式。涉及的公网 IP、宿主机 nginx、路径与证书均是特定部署事实，并非通用模板。

## 一、先理解 MCP、API 和公网网关的分工

MCP 的职责是让远端 Agent **调用经过定义的工具**，而不是取得数据库账号。以 `search_job_candidates` 为例，Agent 提供查询和筛选条件，MCP 转给 API，API 查询数据库并返回岗位证据。Agent 得到的是允许读取的结果，不是任意执行 SQL 的能力。

```text
其他机器的 OpenCode / Agent
  → 公网 HTTPS :443（现有宿主机 nginx、可信 IP 证书）
  → 127.0.0.1:8443（Docker nginx：鉴权、限流、私有 TLS）
  → mcp:8001 → api:8000 → PostgreSQL
```

这里有两层不同的保护：

- **网络边界**：公网只开放既有 HTTPS 443 的指定 `/mcp` 路由；`8008`、`8009`、`8443` 仅监听回环地址，数据库端口不发布。
- **工具权限**：MCP 只提供 `get_knowledge_base_stats`、`search_job_candidates`、`get_job` 三个只读工具。写入、状态修改、SQL、模型凭据都不通过公网 MCP 提供。

公网入口为 `https://106.55.35.201/mcp`，使用 `Authorization: Bearer <访问令牌>`。无令牌能访问到 HTTP 网关，却不能调用工具；浏览器直接打开返回 401，通常代表**入口可达但鉴权拒绝**，不是“网页损坏”。

## 二、为什么使用 HTTPS 和 Bearer 令牌？

HTTPS 保护数据和令牌在传输过程中的机密性及完整性；Bearer 令牌则证明客户端持有访问凭据。**HTTPS 不能替代业务鉴权，Bearer 也不能替代 TLS。**

该服务器复用 Let's Encrypt 的**公网 IP 证书**，客户端用系统正常证书信任链即可；不要设置 `verify=false` 绕过验证。令牌在服务器的：

```text
/home/ubuntu/workspaces/job-rag/runtime/public/access-token
```

文件权限为 0600，应通过 SSH/SCP 等安全渠道提供给被授权调用方，不能写入 Git、聊天记录或客户端代码。内层网关的 `ca.key`、`server.key`、`auth.conf` 也不得分发；容器只挂载实际所需的服务证书、私钥和鉴权映射，**不挂载 CA 私钥**。

当前是**多个使用者共享一枚只读令牌**。这能阻止匿名调用，却不能实现每用户身份、独立限额或逐用户审计；因此不适合当作完整多租户安全方案。

## 三、其他机器怎样连接 OpenCode V2？

调用方先安全获取令牌，例如保存至 `~/.config/job-rag/access-token`，并让即将启动的 OpenCode **服务进程**继承变量：

```bash
chmod 600 ~/.config/job-rag/access-token
export JOB_RAG_TOKEN="$(cat ~/.config/job-rag/access-token)"
```

在 `~/.config/opencode/opencode.jsonc` 中**合并**以下配置（不要覆盖已有其他 MCP 与模型设置）：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "jobrag": {
        "type": "remote",
        "url": "https://106.55.35.201/mcp",
        "oauth": false,
        "headers": {
          "Authorization": "Bearer {env:JOB_RAG_TOKEN}"
        }
      }
    }
  }
}
```

如果 Shell 已经设置环境变量，但 OpenCode 后台服务更早启动，那么服务进程仍可能读不到变量。应在有变量的环境中重启对应服务，或通过该机器自己的安全服务配置注入，再运行 `opencode mcp list` 检查。

**连接 MCP 不等于安装 Agent**：远程 `/jobs` 命令及 DeepSeek agent 需另外从 `.opencode/agents/jobs.md`、`.opencode/commands/jobs.md` 安装/复制，并使用调用方自己的模型账户。服务端不会提供或共享 OpenCode Go 凭据。

## 四、怎样验证是“网络问题”还是“鉴权问题”？

先不带令牌请求：

```bash
curl -i https://106.55.35.201/mcp
```

预期的 401 表明当前路由通常能到达并触发鉴权。若是 TLS 证书错误、超时或连接拒绝，应先检查相应网络/证书层，而不是假定令牌不对。

授权客户端可以运行完整握手与工具查询检查：

```bash
JOB_RAG_MCP_URL=https://106.55.35.201/mcp \
JOB_RAG_TOKEN_FILE=/安全路径/access-token \
  .venv/bin/python scripts/check_mcp.py
```

该脚本不输出令牌，也不写入岗位数据。普通浏览器不会自动附带 Authorization 头；`/mcp` 不是为浏览器阅读设计的网页。

## 五、网关的限流、证书和运维为什么仍需单独管理？

内层网关现配置 `5r/s`、burst 15、最多 10 个并发连接，HTTP 请求体最多 128 KiB。由于宿主机代理会转发访问，限流计数可能按代理来源地址共享，**不是每位用户的独立配额**。限制流量可以减轻滥用和突发负载，但不能替代容量测试。

宿主机 nginx 只增加 `/mcp` 精确路由，原网站与 ACME 验证路径不变；配置位于 `/etc/nginx/snippets/job-rag-mcp.conf`，原站点备份位于 `/etc/nginx/jobrag-backups/`。云安全组无需额外开放 8443/8009；可根据真实调用方进一步设 IP 访问限制。

外层 IP 证书沿用已有 `certbot-renew.timer`；内层私有服务证书有效期 365 天，须到期前续签并重新加载网关和宿主机 nginx；CA 有效期 10 年。公网 IP 变化时需同步调整入口与证书。令牌泄露则应轮换 `auth.conf` 与 `access-token` 并重建网关，让旧令牌失效。

同时管理基础服务和网关：

```bash
sudo docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.public.yml up -d --no-build --pull never

sudo docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.public.yml logs --tail 100 gateway
```

不要将只含基础 compose 文件的 `--remove-orphans` 命令随意用于这个部署，否则可能误删网关容器。

`scripts/setup_public_access.py` 用于当前主机生成私有 TLS 与令牌；`scripts/install_host_nginx.py` 为检查过的既有站点增加路由，拒绝覆盖已有 snippet 并留备份。**它不是可以直接在任意服务器运行的通用安装器**。

这套结构的核心是：**把远端 Agent 的权限限制在指定只读工具内，再用 TLS、令牌、网关和回环监听逐层缩小暴露面。** 它已经可用，但距离分用户鉴权、精细审计和自动证书告警的正式平台仍有距离。
