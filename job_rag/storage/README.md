# 存储层：为什么要把原文、历史版本、索引与招聘状态分开？

想象一条岗位今天写“负责 RAG 系统”，明天改成“负责向量检索与知识图谱”，同时招聘页面暂时无法访问。这里其实发生了三种不同的变化：**招聘描述版本**、**基于描述的检索索引**、**职位是否仍在招**。如果全存在一张没有历史的表里，更新后就无法回答某个结果依据哪一版 JD，也无法区分采集失败与岗位关闭。

`storage/` 为这些对象提供数据模型和持久化基础，不负责判断岗位是否匹配用户。

## 一、数据保存在哪儿？

`database.py` 的 `Database` 读取 `DATABASE_URL`。不配置时使用 SQLite，默认地址为 `sqlite:///runtime/jobs.db`；Docker Compose 使用 PostgreSQL + pgvector，将数据目录持久化到 `pgdata` 卷。注意：`storage/` 是**代码包**，并不是数据库文件所在目录；重排 Python 包位置不会自动迁移数据库文件或容器数据卷。

SQLite 对可选向量使用 JSON 列，PostgreSQL 使用 pgvector 类型。后者提供余弦距离查询能力，但**安装 pgvector 不代表已经配置或调用了 Embedding**。

## 二、五张表分别保存哪种事实？

| 表 | 作用 | 为什么不能混在一起 |
|---|---|---|
| `jobs` | 当前版本的原始字段 `raw`、派生字段 `normalized`、状态、版本及索引签名 | 提供当下可读取的岗位对象 |
| `revisions` | 数据变更时保存此前与当前导入版本的内容 | 能解释岗位文字何时发生变化，不等于每次读取日志 |
| `chunks` | 当前有效索引的分块文字、原文位置、可选向量 | 是从 JD 派生的表示，可以重建；历史分块不会永久保存 |
| `index_tasks` | 某岗位版本、索引签名与任务状态 | 网络模型或分块失败时能重试，而不丢原始岗位 |
| `status_events` | 状态从什么变成什么、依据和时间 | 让“招聘还有效吗”不被“采集成功了吗”替代 |

新 JD 先写 `jobs/revisions` 并登记任务，后续 Worker 成功后更新 `chunks` 和 `indexed_version`。只有岗位版本、索引版本、配置签名都符合条件，检索层才使用相应索引，避免新版岗位配旧版证据。

## 三、为什么招聘状态必须单独维护？

`status.py::set_status()` 接受 `unknown`、`active`、`suspected_expired`、`closed` 四种状态。状态改变时写入 `status_events`，需要非空原因；只有明确标记已确认在招或关闭，才更新成功核验时间。

CSV 的 `status` 是采集结果：“获得了详情文字”不等于 `active`；“打不开网页”也不能可靠证明 `closed`。`last_seen_at` 表示最近被系统观察/导入，`last_verified_at` 表示最近完成明确核验，两者不能混用。更新招聘状态不需要重新生成向量。

## 四、怎样使用和维护？

`database.py` 管理连接、SQLAlchemy ORM、建表和显式迁移；`serialization.py` 将同一岗位统一转换为 API 输出，包括来源、版本和状态；它不负责查询或排序。

~~~bash
job-rag init
# 修改过数据库结构的既有实例：先备份，再按迁移要求执行
job-rag migrate
job-rag reindex
~~~

`create_all()` 不是通用自动迁移器；迁移需要显式执行。当前写入按单写入者设计，避免同时运行多个 import、worker 或 reindex。原始 CSV 无法恢复人工状态历史，备份数据库与备份 CSV 是两项不同的操作；PostgreSQL 可用 `pg_dump`，SQLite 运行中不要仅复制主库文件而忽略 WAL。

下一步看[索引执行](../indexing/README.md)怎样安全替换派生块；在[查询层](../querying/README.md)中可看到为什么精确字面统计与有截断的检索必须分开。