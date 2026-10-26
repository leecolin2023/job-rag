# 为什么 RAG 不能只存一张“岗位与向量”表？

设想一家公司今天的 JD 写“熟悉 Python 即可”，明天改成“必须会部署 vLLM”；同一天又有人报告岗位链接失效。如果数据库只保存一条最新文本和一条向量，会同时发生两种混淆：**旧向量可能被用于新岗位**，而“链接访问失败”可能被误记为“职位关闭”。

Job-RAG 的存储设计因此区分三条时间线：**岗位内容怎么变化、检索索引更新到哪一版、招聘状态有哪些核验依据**。

## 一、岗位的当前事实与历史版本为什么要同时保存？

`jobs` 保存当前岗位原文字段 `raw`、可比较字段 `normalized`、`version`、来源身份、最近观察时间、招聘状态与索引版本；`revisions` 保存每次新增或导入内容发生变化时的版本快照。

例如某职位从 v1“会 Python”更新为 v2“需部署 vLLM”，当前回答应使用 v2，但事后有人质疑旧回答时，我们仍需知道当时读取过怎样的 JD。保留历史版本解决可追溯问题；它并不等于记录了用户每一次访问页面的事件。

`source:job_id` 是当前岗位的键，不同来源的相似招聘不会因文字相似就自动合并，因为这样可能误删不同职位。

## 二、为什么索引没有就绪时宁愿暂时不返回？

`chunks` 是从 JD 派生的检索块及可选向量；`index_tasks` 记录某岗位版本和某个构建配置的任务。考虑 v2 已写入，但仍只有 v1 分块的短暂阶段：如果直接允许检索返回，页面显示 v2 岗位详情，证据却来自 v1，就会出现难以发现的错配。

代码把 `indexed_version` 与 `index_signature` 存在岗位记录中；检索要求它们与当前 `version` 和当前配置对应，索引任务完成后才更新。`chunks` 可以重建和原子替换，不作为永久的历史块仓库；历史招聘文本主要保存在 `revisions`。

这是一种以短时不可检索换取**来源与证据版本一致**的选择。现阶段没有自动蓝绿索引切换，生产更新需要意识到这个可用性代价。

## 三、招聘状态为什么是一份独立的数据？

`status_events` 记录 `unknown / active / suspected_expired / closed` 之间的变化、理由和时间。它不能依赖原始 CSV 里的 `status`：采集成功表示“得到文字”，不表示“已经确认在招”；链接打不开也可能只是网络错误。

`last_seen_at` 表示最近导入观察，`last_verified_at` 表示完成明确在招/关闭核验的时间。如果重新导入新 JD 就自动恢复 `active`，之前的人工下架判断将被悄悄抹掉，因此导入和状态核验分开处理。状态更新也不必重新调用 Embedding，因为它没有改变检索块的正文。

## 四、SQLite、PostgreSQL 和 pgvector 解决的是哪一层问题？

数据库由 `DATABASE_URL` 选择。本地默认 `sqlite:///runtime/jobs.db`，适合小规模测试；Docker 使用 PostgreSQL 与持久化卷 `pgdata`。PostgreSQL 的 `pgvector` 提供向量类型和距离运算；SQLite 则可用 JSON 保存向量并在应用内计算。

**pgvector 不会自动读取 JD、生成 Embedding 或判断岗位合适。** 这些分别属于[分块](../chunking/README.md)、[模型客户端](../providers/README.md)和[检索](../retrieval/README.md)。存储层只让数据有稳定位置、版本和关系。

## 五、为什么文件目录变化不等于数据库迁移？

`storage/database.py` 定义 SQLAlchemy ORM 和 `Database`，负责连接、初始化和显式迁移；`status.py` 保存人工招聘状态变更；`serialization.py` 把同一份岗位按约定输出给 API、检索和统计。代码目录并不保存数据库文件，移动 Python 模块不会自动搬动数据卷。

~~~bash
job-rag init
# 既有数据库有 schema 差异时，先备份，再明确迁移、重建
job-rag migrate
job-rag reindex
~~~

`create_all` 负责初始建表，不是任意结构变化的自动迁移器。CSV 无法恢复 `status_events` 等人工记录，因此完整备份不能只保留 CSV。项目目前要求串行写入，避免并发 import / worker / reindex 导致版本竞争。

这层要守住的机制是：**原始事实可以更新，派生索引可以重建，核验依据不应被二者覆盖**。