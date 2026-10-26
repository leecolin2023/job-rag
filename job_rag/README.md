# 代码目录导航

按数据处理阶段组织，代码目录不等于运行数据的存储目录：

| 阶段 | 目录 | 说明 |
|---|---|---|
| 外部原始输入 | [`../data/`](../data/README.md) | CSV 字段、采集边界、原文保留 |
| 预处理 | [`preprocessing/`](preprocessing/README.md) | 整份校验、规则标准化、事务内增量导入 |
| 持久化 | [`storage/`](storage/README.md) | 数据模型、实际保存位置、版本与招聘状态 |
| 结构化分块 | [`chunking/`](chunking/README.md) | 原文对齐的章节、条目与规则标签 |
| 索引执行 | [`indexing/`](indexing/README.md) | 任务、可选 Embedding 与索引替换 |
| 服务接口 | [`interfaces/`](interfaces/README.md) | FastAPI、只读 MCP、CLI 与网页资源 |
| 相关性检索 | [`retrieval/`](retrieval/README.md) | BM25/可选向量、两层融合、证据及回答 |
| 精确数据查询 | [`querying/`](querying/README.md) | 公共硬过滤、全库字面计数、分页、全文和统计 |
| 模型接入 | [`providers/`](providers/README.md) | 在线 Embedding/Chat HTTP 客户端，不是 ORM 模型 |
| 离线实验 | [`experiments/`](experiments/README.md) | 冻结语料、检索对照、重排、标注与重算 |

顶层只保留 `config.py`（环境配置与索引签名）、`__init__.py`（包声明）及本文档。原有平铺业务模块已删除，不提供兼容层；代码与测试统一使用上表中的模块。各目录的 `__init__.py` 仅声明包或公共 API，不另设一套实现。

### 在线调用关系

```text
Agent → MCP → FastAPI → retrieval/（候选检索与证据）
                     → querying/ （确定性全库查询、全文读取）
CLI ─────────────────→ 各阶段业务模块

retrieval/ → querying/filters.py + storage/serialization.py
retrieval/、indexing/ → providers/client.py（按配置调用模型）
各数据访问模块 → storage/ → PostgreSQL / SQLite
```

`querying/` 不依赖 `retrieval/`；字面计数不会间接经过 BM25、向量或 Chat。API/MCP 不各自重复实现岗位查询。网页/API 的可选 Chat 回答与调用方 Agent 回答仍是两条独立路径。

安装入口配置在 `../pyproject.toml`：`job-rag` → `interfaces.cli:main`，`job-rag-mcp` → `interfaces.mcp_server:main`，实验命令仍为 `experiments.cli:main`。入口变更后重新安装包；接口 URL、命令名和参数保持不变。

本次重组不搬动数据库、不改变表结构或默认配置、不改写原始数据与历史实验，也不自动部署服务。
