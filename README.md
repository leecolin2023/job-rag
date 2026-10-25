# Job-RAG

AI 招聘岗位知识库初版：网页查询、结构化过滤、关键词/语义混合检索、来源引用、增量导入与状态管理。

**版本：0.1.0** · [当前成果与已知边界](docs/current-status.md) · [更新记录](CHANGELOG.md) · [公网接入](docs/remote-access.md) · [执行记录分析](docs/observability.md)

**开发中：结构化分块与Qwen3.7实验。** 新版代码提供显式数据库迁移、源文可追溯章节/条件分块，以及独立的[两阶段实验工具](experiments/README.md)。详见[分块与迁移](docs/structured-chunking.md)、[实验协议](docs/embedding-experiments.md)。当前在线容器仍为0.1版本，尚未切换；现有数据库使用新版前必须先备份、`job-rag migrate`、再重建索引。

[第一轮真实Embedding实验已完成](docs/recall-pilot-2026-10-25.md)：种子标注下没有证据支持Embedding全面优于BM25，尚未执行全量Rerank轮次或切换线上索引。

**当前服务器公网 MCP：`https://106.55.35.201/mcp`（需要 Bearer 令牌）。** 远程客户端配置、安全取令牌、证书及运维说明见 [公网访问文档](docs/remote-access.md)。原始 API/MCP 端口仍仅监听本机。

## Docker 服务化与 DeepSeek harness（推荐）

```text
OpenCode / DeepSeek V4.1 Flash
  └─ MCP :8009/mcp（只读工具）
       └─ API :8008（检索、岗位详情、网页）
            └─ PostgreSQL + pgvector（内部网络、持久化卷）
```

```bash
python3 scripts/setup_docker_env.py
sudo docker compose --env-file .env.docker up -d --build --wait
```

`setup_docker_env.py` 只在文件不存在时生成随机数据库密码，`.env.docker` 权限为 0600，不提交 Git。`init` 是一次性导入任务，退出码 0 为正常；`db`、`api`、`mcp` 为后台服务，配置了 `restart: unless-stopped`。数据库不映射宿主机端口，API 和 MCP 仅绑定回环地址。

访问：网页 <http://127.0.0.1:8008>，API 文档 <http://127.0.0.1:8008/docs>，MCP Streamable HTTP <http://127.0.0.1:8009/mcp>。

### OpenCode 配置

```bash
opencode mcp add jobrag --global --url http://127.0.0.1:8009/mcp
opencode mcp list
```

项目提供 `.opencode/agents/jobs.md` 和 `.opencode/commands/jobs.md`。在此项目的 OpenCode 中运行：

```text
/jobs 帮我找广州月薪下限20K以上、做企业知识库问答的岗位
```

该命令显式选择 **`opencode-go/deepseek-v4.1-flash`**，使用当前已连接的 OpenCode Go 账户及其额度，不改变其他对话的默认模型，不向容器复制凭据。当前环境的免费入口 `opencode/deepseek-v4.1-flash-free` 拒绝调用，因此未使用它。也已在当前用户的全局 agents/commands 中安装只读 `jobrag` 助手与 `/jobs` 命令，可从其他项目使用；项目内版本由仓库维护。

**这里不是用 DeepSeek 生成 Embedding。** DeepSeek 是调用工具的 harness 模型，负责理解问题、提出 2—4 条同义改写、阅读证据并排序；服务负责严格条件过滤、多查询 BM25/RRF 候选召回。工具明确返回 `semantic_assessment: caller_llm_required`，不将词法分数称为语义分数。其他支持 MCP 的 DeepSeek harness 也能连接同一 URL，并按 MCP 初始化说明执行同样流程。

真正的向量召回仍需另外配置专用 Embedding 服务；可设置 `.env.docker` 的 `EMBEDDING_*` 并在同一配置下重新索引。仅连接 MCP 并不会使网页自动具备 DeepSeek 语义理解；网页/API 默认仍返回关键词结果。

三个只读 MCP 工具：

| 工具 | 用途 |
|---|---|
| `get_knowledge_base_stats` | 查看数据规模、地区、状态及索引情况 |
| `search_job_candidates` | 原问题 + 最多4条改写 + 硬条件，多查询去重召回并返回证据 |
| `get_job` | 完整原文、最新状态和版本，最终推荐前复核 |

管理 API 不暴露为 MCP 工具。回环服务没有读鉴权，不能直接映射到公网；远端 harness 应使用 SSH 转发，或通过带认证的反向代理部署。OpenCode MCP 无 OAuth，因为该回环服务本身无登录流程；若以后接入认证代理，按其方式配置认证。

### Docker 日常运维

```bash
# 查看状态、日志
sudo docker compose --env-file .env.docker ps -a
sudo docker compose --env-file .env.docker logs --tail 100 api mcp

# CSV 修改后重新构建，并手动执行一次同步；不要并发启动多个写入任务
sudo docker compose --env-file .env.docker build init
sudo docker compose --env-file .env.docker run --rm --no-deps init
sudo docker compose --env-file .env.docker up -d --no-deps api mcp

# 重试索引 / 重建（使用 API 容器的数据库与模型配置）
sudo docker compose --env-file .env.docker exec api job-rag worker
sudo docker compose --env-file .env.docker exec api job-rag reindex

# 人工确认岗位状态
sudo docker compose --env-file .env.docker exec api job-rag status 岗位ID closed --reason '页面确认关闭'

# 备份（生成文件包含完整业务数据，注意权限）
sudo docker compose --env-file .env.docker exec -T db pg_dump -U jobrag -d jobrag > jobs-backup.sql
```

已有 SQLite 库不会被删除，但也不会自动迁移其人工核验记录。正式切换有历史状态的实例时，需要先备份并迁移，不能仅重导 CSV。

### 当前服务器的镜像网络限制

此服务器允许 `sudo docker`，但 Docker daemon 未继承终端的 HTTP 代理，直接从 Docker Hub 拉取会超时。无需修改 socket 权限或重启全局 daemon，可使用项目的镜像加载工具（需先完成下面的 Python 环境安装）：

```bash
.venv/bin/python scripts/pull_image_via_proxy.py python:3.12-slim
.venv/bin/python scripts/pull_image_via_proxy.py pgvector/pgvector:pg16
sudo --preserve-env=HTTP_PROXY,HTTPS_PROXY,NO_PROXY docker build --network host \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY -t job-rag:local .
sudo docker compose --env-file .env.docker up -d --no-build --pull never --wait
```

加载工具只支持公开 Docker Hub 镜像，使用当前终端代理，核验下载内容的 SHA256，再交给 `docker load`。代理值不写入项目配置或镜像 Dockerfile。镜像依赖仍需定期更新与安全审计。

## 快速启动（无需模型密钥）

需要 Python 3.10+。在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
job-rag import data/jobs.csv
job-rag serve
```

打开 <http://127.0.0.1:8000>；API 文档：<http://127.0.0.1:8000/docs>。

默认使用 `runtime/jobs.db`（SQLite），运行时数据库、向量和密钥均不提交 Git；基础岗位 CSV 已包含在仓库中。无模型配置时使用 **BM25 关键词检索 + 可核对的岗位来源列表**，不是语义检索，也不是 LLM 生成。中文检索使用字符二元组和少量别名，适合初版，但不等价于专业中文分词。配置模型后才启用完整的语义 RAG。

远程服务器默认只监听回环地址，可通过 SSH 转发访问：

```bash
ssh -L 8000:127.0.0.1:8000 用户名@服务器地址
```

### 可选：Embedding 与生成模型

将 `.env.example` 复制为 `.env`，配置 OpenAI-compatible 服务：

```dotenv
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=你的密钥
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_VERSION=v1
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=你的密钥
CHAT_MODEL=你的可用聊天模型
```

之后运行 `job-rag reindex` 并重启服务。在网页勾选“使用大模型解释匹配结果”开启生成。仅配置 Embedding 也可以混合检索；仅配置 Chat 则基于关键词检索结果生成回答。

- Embedding 模型须原生输出配置的维度，客户端不发送 `dimensions` 参数，以兼容其他服务。
- 修改模型、服务地址、维度或预处理规则后须修改版本并重建。签名不匹配的旧向量不参与检索。
- 岗位分块会发送到 Embedding 服务；问题和命中的岗位证据会发送到 Chat 服务。配置前确认服务的数据政策。
- 模型服务失败时查询降级为关键词检索/来源列表；索引失败保留任务，可重试，不切换到半成品版本。
- 模型回答属于辅助解释；引用编号有基础校验，但不能保证每个生成结论都正确，仍应核对原文。

### 可选：已有 PostgreSQL + pgvector

如不使用上面的完整 Docker 栈，可在 `.env` 设置你已有数据库的 `DATABASE_URL=postgresql+psycopg://用户名:密码@主机:端口/数据库`，然后重新导入并启动服务。首次建表需要 `CREATE EXTENSION vector` 权限；正式部署可由 DBA 预先创建扩展。

PostgreSQL 使用 pgvector 精确余弦距离；SQLite 使用 JSON 向量在应用内计算距离。当前规模无需 ANN 索引，关键词评分也在应用内进行；数万岗位后应改为数据库候选召回和专业中文全文索引。已有数据库的数据卷密码不会被环境变量自动重置。

## 日常维护

### 新增或更新岗位

```bash
job-rag import data/jobs.csv
# 也可以导入另外一份相同字段格式的增量文件：
job-rag import /path/to/new_jobs.csv --source boss
# 先落库，稍后处理索引：
job-rag import /path/to/new_jobs.csv --no-index
job-rag worker
```

按 `(source, job_id)` upsert，整份文件先验证，再原子导入。重复 ID、缺少必填列或列数错误时整批拒绝。文件内不允许同一个 ID 出现两次；多个来源可使用各自的 `--source`。

- 原始行不变：只更新本地观察时间，不新增版本、不生成向量。
- 原始行变化：保留旧版本，记录新版本，创建同事务索引任务。
- 只有采集日期等元数据改变：更新版本，但检索文档相同且模型签名相同则复用向量。
- 岗位描述改变：原子替换该岗位全部分块，删除多余旧块；新索引完成前该岗位暂不参与检索，不展示旧内容。
- 索引任务失败：任务状态为 `failed`，再次运行 `worker` 重试。任务可幂等重放；异常仅保存类型，避免泄露服务密钥。
- 增量文件没出现的岗位不自动关闭。即使是完整快照，也建议先核验缺失原因。

**本版本按单写入者设计：不要并发执行多个导入/worker/reindex，使用管理导入 API 时也应串行提交。** `worker` 是单次运行命令，不是后台常驻队列。可通过 cron 定期执行，但应由运维使用文件锁避免任务重叠。

### 岗位有效性

```bash
job-rag status 岗位ID active --reason '2026-10-25 人工打开页面确认在招'
job-rag status 岗位ID suspected_expired --reason '多次访问失败，暂不能确认是否关闭'
job-rag status 岗位ID closed --reason '原页面明确显示职位已关闭'
```

状态变更不需要重新 Embedding；默认检索仅包含 `unknown` / `active`，历史查询才包含 `closed` / `suspected_expired`。重新导入不会自动恢复已关闭岗位。`active_only` 只返回确认在招的岗位。

初始 593 条全部为 `unknown`，即使原 `status` 为“已获取描述（详情字段已核验）”也不自动认定在招。无描述的 1 条仍保留供审计，但无检索分块。网页“仅确认在招”初始可能无结果，这是正常现象。

`last_seen_at` 表示本系统最近导入观察时间，不是页面在线证明；`last_verified_at` 仅在明确设置 `active` / `closed` 时更新，具体核验依据见状态历史。原采集时间始终保留在 `collected_at`。

本版不包含招聘网站爬虫、自动在线核验或自动截止日期判定，也不承诺 `active` 永久有效；需定期依据合法获取的新数据或人工核验维护状态。超时、验证码和 403 不能直接当作关闭证据。

### 查询

```bash
job-rag search '广州 RAG' --min-salary 20000 --skills Python RAG
job-rag search '大模型应用' --active-only --generate
```

网页支持城市、最低月薪、薪资区间规则、经验年数、必含技能与状态过滤。经验筛选指“岗位最低年限不高于我的年限”；未知年限不参与此类严格筛选。技能列表采用明确文本匹配，输入的每项都必须出现；问题文本本身主要用于相关性排序，不保证自动识别所有硬条件。

仅保守识别问题里的已知城市、`20K以上` 这样的薪资下限以及 `3年经验` 这样的候选人年限；复杂的地区或条件组合请通过表单/API 明确指定。薪资未知、面议、日薪、时薪不会混入月薪筛选；多薪信息单独存储，不默认推算年包。学历为原字段的精确筛选，不推断等价学历。

结果按岗位 ID 聚合，每个岗位最多提供两个证据分块；同描述的不同平台 ID 不强行合并，避免误删真实职位。生成完成后会再次检查岗位版本和状态，发现变化则要求重新查询。

### API

| 路径 | 功能 |
|---|---|
| `GET /health` | 健康检查 |
| `GET /api/stats` | 岗位、状态、索引任务统计 |
| `POST /api/search` | 检索 / 可选生成，参数见 `/docs` |
| `POST /api/candidates` | 多查询候选召回，由调用模型阅读证据完成语义判断 |
| `GET /api/jobs/{job_id}?source=boss` | 岗位原文、版本目录、状态历史 |
| `POST /api/import?source=boss` | CSV 原始请求体导入，最大 20 MiB，需管理令牌；之后运行 worker |
| `POST /api/jobs/{job_id}/status` | 更新有效状态，需管理令牌 |

```bash
curl http://127.0.0.1:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"广州 RAG","min_salary":20000,"skills":["Python","RAG"],"limit":5}'
```

管理 API 默认关闭。设置 `.env` 中的 `ADMIN_TOKEN` 后重启，携带 `Authorization: Bearer <令牌>` 使用。网页只提供只读检索，不暴露管理令牌。不要将密钥写入 Git、聊天或浏览器脚本。

### 测试与备份

```bash
pytest -q
```

测试覆盖真实 CSV 导入、BOM/多行描述、重复导入、版本替换、元数据复用、索引失败重试、模型签名隔离、结构化过滤、状态关闭/历史查询、生成期间状态变化与管理鉴权。模型调用使用替身测试，无需付费；不等于已验证你的模型供应商。

Docker 部署后的只读 MCP 检查与隔离数据库集成检查：

```bash
.venv/bin/python scripts/check_mcp.py
sudo docker compose --env-file .env.docker run --rm --no-deps \
  -v "$PWD/scripts:/checks:ro" api python /checks/check_postgres.py
```

PostgreSQL 检查使用唯一命名的临时数据库，不改岗位业务库；验证真实 pgvector 写入与距离查询，但向量来自测试替身，并非真实 Embedding 模型。2026-10-25 已通过 36 项 pytest、上述两项检查，以及 `opencode-go/deepseek-v4.1-flash` 实际 MCP 查询/改写/详情复核链路。真实供应商的向量生成仍未配置。

当前 `create_all` 仅负责首次建表，不是数据库迁移工具。修改表结构前备份并编写迁移，不要直接删除正式数据库重建。SQLite 停止写入后可用 Python `sqlite3.Connection.backup` 做一致性备份（不要运行中只复制 `.db` 而遗漏 WAL）；PostgreSQL 使用 `pg_dump`。CSV 无法还原人工核验记录，必须同时备份运行时数据库。

当前公网 MCP 已增加 HTTPS、Bearer 鉴权、限流和请求大小限制，配置见 [公网访问文档](docs/remote-access.md)。这仍不等同于完整生产平台：暂未提供分用户鉴权、全量请求审计、自动备份及数据库迁移工具，不应直接用于多租户敏感数据场景。

## 数据来源与范围

来源：`BOSS直聘_AI岗位数据库_清洗规整版_20261024` 中的 **「01_岗位主表_规整」**（更新至 2026-10-25 的岗位详情），并从「历史_岗位去重总表」继承首次采集关键词和广州标记。

本次快照共 **593 条职位**，其中 **592 条有实际岗位描述**，**1 条因原招聘链接失效未取得描述**。所有岗位保留在一份 CSV 中，无丢失、无重复职位 ID。

数据仅供学习、研究与分析。招聘状态、薪资与岗位要求可能发生变化，不代表当前职位仍在招聘。

## 数据结构

```text
data/
└── jobs.csv  # 唯一的标准化岗位数据源，593 条
```

`data/jobs.csv` 保留 16 个已有字段：

`job_id, title, company, location, salary, experience, education, url, description, status, collected_at, keywords, first_keyword, keyword_count, is_guangzhou, address`

- `job_id`：来自 BOSS 职位 ID，是全局唯一的更新/关联键。
- `description`：岗位职责与任职要求原文，**不做摘要、语义改写或无依据的文本修复**。链接失效且未取得描述的 1 条记录，其值为空，不使用原表中的占位符 `6`。
- `status`：来自最新主表，明确记录是否取得描述及失败情况。
- `first_keyword`、`is_guangzhou`：通过相同 `job_id` 从历史去重总表关联得到。

**文件编码**：UTF-8 with BOM（`utf-8-sig`）。按照标准 CSV 转义，岗位描述中的逗号、引号、换行均保留。不能直接使用换行符判断记录条数，建议使用 Python `csv` 或 `pandas.read_csv`。

## 更新与检索约定

1. `jobs.csv` 是初始岗位内容的标准导入源，无需维护分拆的有/无详情文件或独立的 `documents` 目录。运行时数据库保存历次导入、派生索引和人工核验记录。
2. 以 `job_id` 做增量更新（upsert）；不使用 CSV 行号作为岗位主键。
3. 生成 Embedding 前只选择 `description` 非空的岗位。文本由程序动态组装为检索 Document，不直接修改原始描述。
4. 地区、薪资、经验等字段可用于结构化筛选，岗位职责与技术要求用于语义检索。
5. 运行导入后生成检索分块；只有配置 Embedding 服务时才生成向量。原始 CSV 不会被程序改写。

## 数据与隐私

此仓库为公开仓库。CSV 不包含专门的招聘者身份/活跃信息字段与企业工商登记原文。请勿提交 API Key、个人简历或其他私有资料。原始 Excel 建议妥善保存于非公开位置。
