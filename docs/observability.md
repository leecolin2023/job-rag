# 执行记录与分析

## 三种不同记录

| 记录 | 存放位置与用途 |
|---|---|
| Harness 会话 | 调用方 OpenCode 的会话记录，包含输入、可见回答和工具调用；用于分析查询改写、候选结果和最终选择 |
| 服务访问日志 | Docker API/MCP/网关与宿主机 nginx 的访问、运行日志，主要用于排错和 HTTP 状态分析，不是完整工具请求审计 |
| 岗位业务历史 | 运行时数据库中的 revisions、status_events、index_tasks，分析岗位更新、核验与索引状态 |

其他机器调用时，模型会话主要保存在**调用方 harness**，不会自动同步到岗位服务器。当前未实现全量请求/响应审计和跨服务 trace ID 关联。

## 导出 OpenCode 测试轨迹

在持有对应 OpenCode 会话的机器运行：

```bash
python3 scripts/export_test_trace.py ses_你的会话ID
```

脚本通过 OpenCode V2 API 读取，既不直接访问也不修改 OpenCode 数据库；默认只导出首轮至第一个 idle 事件，避免混入后续无关对话。输出位于：

```text
runtime/analysis/<session_id>/
├── timeline.md
├── trace.json
└── tools.jsonl
```

导出包含可观察输入、回答、工具代码/参数、返回结果、状态和已记录的时间；排除私有推理、供应商原生载荷及明显密钥字段，并对 Bearer 字串做基础脱敏。这不是完整内部思维链导出，也不是通用的秘密扫描器。分享前仍需人工检查工具结果中的个人信息或其他敏感内容。

目录已由 Git 忽略，脚本使用受限文件权限，且拒绝覆盖已有导出目录。Code Mode 下工具可能显示为 `execute`，其中的 `input.code` 和工具返回结果包含实际 MCP 调用信息。

本机 OpenCode 默认路径可用以下命令确认；不要直接修改活动数据库：

```bash
opencode debug paths db
opencode debug paths log
```

## 服务端日志

```bash
sudo docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.public.yml logs --tail 100 api mcp gateway
```

日志不应记录 Authorization 令牌；不要为了排障将密钥、完整私人简历或全量供应商请求写入日志。未来如增加审计，应明确数据保留周期、脱敏、访问控制和调用方隐私边界。
