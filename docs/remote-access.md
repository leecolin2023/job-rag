# 公网 MCP 访问（当前服务器）

## 连接信息

- **MCP Streamable HTTP URL：`https://106.55.35.201/mcp`**（标准 HTTPS 443）
- 鉴权：`Authorization: Bearer <访问令牌>`。
- 令牌文件：服务器 `/home/ubuntu/workspaces/job-rag/runtime/public/access-token`，权限 0600；通过 SSH/SCP 或其他安全渠道分发给授权调用方，不要发到公开聊天或 Git。
- 公网入口复用本机已经存在的 Let's Encrypt **IP 证书**，客户端使用常规系统信任即可，无需安装私有 CA，也不要设置 `verify=false`。
- 本服务器的 OpenCode 继续使用回环 MCP，不受公网入口影响。

只读工具为 `get_knowledge_base_stats`、`search_job_candidates`、`get_job`。不提供公网导入、状态修改、SQL 或模型凭据访问。

## 其他机器上的 OpenCode V2

安全取得令牌后，在启动 OpenCode 后台服务前设置 `JOB_RAG_TOKEN`。例如令牌保存在调用方 `~/.config/job-rag/access-token` 时：

```bash
chmod 600 ~/.config/job-rag/access-token
export JOB_RAG_TOKEN="$(cat ~/.config/job-rag/access-token)"
```

在调用方的 `~/.config/opencode/opencode.jsonc` **合并**以下设置，保留已有内容：

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

环境变量必须对 **OpenCode 服务进程** 可见，不只是对当前 shell 可见。若已有后台服务运行且未继承变量，需在已设置该变量的终端重启服务再检查 `opencode mcp list`，或通过该机器服务的环境配置安全注入令牌。不要在配置中写明文密钥。

远端 `/jobs` 命令和 DeepSeek agent 不是 MCP 自动安装的：如需同样流程，可将项目 `.opencode/agents/jobs.md`、`.opencode/commands/jobs.md` 放入对应项目，并连接该调用方自己的 OpenCode Go 账户。其他 DeepSeek harness 按自身 MCP 客户端方式配置 URL 与 Authorization 头即可；服务不共享服务器的模型账户或额度。

## 验证

无令牌应返回 `401`（这是公网可达且鉴权生效的表现）：

```bash
curl -i https://106.55.35.201/mcp
```

已安装本项目依赖的授权调用方可执行完整的 MCP 握手/工具调用检查：

```bash
JOB_RAG_MCP_URL=https://106.55.35.201/mcp \
JOB_RAG_TOKEN_FILE=/安全路径/access-token \
  .venv/bin/python scripts/check_mcp.py
```

检查不会输出令牌，也不写入岗位数据。普通浏览器打开 URL 不会自动附带令牌，因此看到 401 正常；这不是网页入口。

## 实现与维护

```text
其他机器 → 公网443（现有宿主机 nginx，可信IP证书）
        → 127.0.0.1:8443（Docker nginx，令牌校验、限流、私有TLS）
        → mcp:8001 → api:8000 → PostgreSQL
```

- 仅在已有 HTTPS server 中增加 `/mcp` 精确路由，现有网站及 ACME 验证路径不变。
- 宿主机 nginx 包含 `/etc/nginx/snippets/job-rag-mcp.conf`；原站点修改前备份在 `/etc/nginx/jobrag-backups/`。
- `8008`、`8009`、`8443` 都仅监听回环；数据库端口不发布。无需在云安全组新增 8443/8009，只需原有 HTTPS 443 可达。可按实际调用方 IP 进一步限制访问。
- `runtime/public/ca.key`、`server.key`、`auth.conf` 均不得分发。内层网关容器只挂载服务证书、服务私钥和鉴权映射，**不挂载 CA 私钥**。
- 使用 `5r/s`、burst 15、最多10个并发连接的内层网关保护；宿主机代理后这些限制可能按代理地址共享，不是独立用户配额。支持最多128 KiB请求；大批查询应分批进行。
- 外层 IP 证书沿用现有 `certbot-renew.timer` 续期机制，不修改现有证书或续期流程。内层私有服务证书有效期365天，需在到期前重新签发并重新加载网关及宿主机 nginx；CA有效期10年。公网IP变化时也需重新配置证书和入口。
- 令牌泄露需立即轮换 `auth.conf` 与 `access-token` 并重建网关容器，使旧令牌失效。所有客户端共享当前只读令牌，没有分用户审计或配额，勿用于多租户敏感数据场景。

服务管理（不要将 `--remove-orphans` 用于只包含基础配置的命令，否则可能删除网关）：

```bash
sudo docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.public.yml up -d --no-build --pull never

sudo docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.public.yml logs --tail 100 gateway
```

本机部署使用 `scripts/setup_public_access.py` 生成私有TLS及令牌，`scripts/install_host_nginx.py` 为经过检查的本机既有站点追加路由：该安装脚本不是通用配置替换工具，会拒绝覆盖已有 snippet，并保留原站点备份。不要在其他机器不经检查直接运行。
