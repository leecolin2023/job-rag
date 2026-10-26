# 数据库存储与招聘状态

本目录负责数据模型、连接、初始化、显式迁移和招聘状态记录；不负责 CSV 校验、字段解析或正文分块。

```text
storage/
├── database.py    # ORM 模型、Database、初始化与迁移
├── status.py      # 招聘状态变更与依据记录
├── serialization.py # 检索、全文及全库查询的公共岗位输出结构
└── __init__.py    # 公共模型与数据库入口
```

数据库实现统一位于 `storage/database.py`，公共入口由 `storage/__init__.py` 导出，不保留根目录旧模块。本次目录重组不改变表结构或数据位置，不需要因为移动代码而迁移数据库或重建索引。

## 数据实际保存在哪里？

由 `DATABASE_URL` 决定，而不是保存在本代码目录。

| 运行方式 | 保存位置 |
|---|---|
| 本地默认 | SQLite：`sqlite:///runtime/jobs.db`，路径相对进程工作目录；在项目根目录启动时为项目下的 `runtime/jobs.db` |
| 自定义配置 | `DATABASE_URL` 指向的数据库，可能不同于默认值 |
| 仓库 Docker Compose | PostgreSQL + pgvector；服务内 `/var/lib/postgresql/data`，由命名卷 `pgdata` 持久化，Docker 实际卷名通常带 Compose 项目前缀 |

`data/jobs.csv` 是外部输入文件；数据库保存导入后的原始字段、派生字段与版本。数据库文件、卷和实验缓存不应提交 Git。修改代码目录不会搬动或备份这些数据。

不要在文档或日志中粘贴包含数据库密码的连接串。备份、迁移、删除数据和调整卷需要单独操作，不能用重新导入 CSV 代替完整备份。

## 主要表

| 表 | 内容 |
|---|---|
| `jobs` | 当前岗位：唯一键、`raw` 原始字段、`normalized` 派生字段、版本、招聘状态、观察与核验时间、索引就绪信息 |
| `revisions` | 岗位每次新增或导入字段变化时的原始字段、标准字段及版本；不等于完整的每次观察事件日志 |
| `chunks` | 当前已写入索引的正文块、原文对齐信息与可选向量；重建时替换，历史块并非永久保留 |
| `index_tasks` | 岗位版本与索引签名对应的任务状态、尝试次数和脱敏错误类型 |
| `status_events` | 招聘状态变更的前后值、依据和时间 |

SQLite 用 JSON 保存可选向量；PostgreSQL 用 pgvector 类型。原始 JD 留存在 `jobs.raw` 与相应 `revisions.raw`，不会被索引结果覆盖。

## 招聘状态单独维护

`storage/status.py::set_status()` 支持 `unknown`、`active`、`suspected_expired`、`closed`，变更必须提供非空依据。新岗位为 `unknown`；只有确认 `active` 或 `closed` 时才更新成功核验时间。

CSV 的 `status` 是采集结果，与此处 `job_status` 不同。页面失效、搜索不到或采集成功都不能自动等同于招聘已结束或正在招聘。

## 调用入口

```python
from job_rag.storage import Database, Job, Revision
from job_rag.storage.status import set_status
```

初始化及迁移命令保持原样。结构迁移仍须显式执行并先备份；导入、索引和状态管理是不同职责，分别见[预处理](../preprocessing/README.md)、[索引执行](../indexing/README.md)。
