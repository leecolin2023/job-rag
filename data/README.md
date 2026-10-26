# 原始岗位数据：知识库为什么必须保留原文？

Job-RAG 的第一个输入不是向量，而是一份可以回溯的招聘资料。假如系统回答“某岗位要求 vLLM 生产部署”，读者最终需要看到招聘方实际写了什么，而不是只能看到模型加工后的标签。因此，`data/jobs.csv` 保留从外部采集流程整理来的岗位信息，后续清洗、分块和模型分析都不回写这份文件。

## 一、数据从哪里来，到哪里去？

本项目**不负责爬取招聘网页**。外部流程先取得岗位和详情，整理成标准 CSV；`preprocessing` 负责校验、标准化并导入数据库；`chunking` 与 `indexing` 在导入之后建立可检索的派生表示。数据库保留岗位版本与状态，`retrieval` 或 `querying` 再提供不同形式的查询。

~~~text
外部采集 → data/jobs.csv → 校验与导入 → 当前岗位/历史版本
                                         ↓
                                  分块与可选向量索引
                                         ↓
                                    查询和证据回溯
~~~

CSV 是“这次拿到了什么”的快照，不是实时招聘市场，也不等于系统数据库的全部历史。系统不会因为后续 CSV 没出现某条岗位就将它自动关闭。

## 二、一条岗位记录包含什么？

当前文件快照有 **593 条不同 job_id，16 个字段，其中 592 条有 description、1 条正文为空**。这是文件规模，不是实时在招数量。

最重要的字段是 `job_id`、`description`、`url`、`collected_at`。ID 用于同来源的更新关联；description 保留完整岗位描述；URL 提供回查入口；采集日期说明信息的新旧程度。`title`、`company`、`location`、`salary`、`experience`、`education` 是面向用户和结构化过滤的原始字段；`address` 提供补充地址。

`status` 描述的是**采集是否取得内容**；`keywords`、`first_keyword`、`keyword_count`、`is_guangzhou` 是外部采集留下的辅助信息。它们不是岗位的完整技能要求，也不能证明岗位仍在招聘。数据库另行维护 `job_status`，见[招聘状态说明](../job_rag/storage/README.md)。

## 三、为什么将原文和派生结果分开？

例如，原文写“有模型部署经验者优先”。检索时可能提取出“部署”“模型”这些词，也可能由规则附上 `preferred` 标签。但标签存在误判可能；如果丢弃原句，后来就无法核对“优先”是否曾被错误写成“必须”。

所以导入器把原始字段存进数据库的 `raw`，将薪资、城市、经验等确定性解析结果存进 `normalized`，将分块、原文偏移及向量存到独立索引里。修复规则或更换模型时可以重新构建派生数据，不必修改已经取得的招聘文字。这里的“原文”指 CSV 内的详情文字，不是网页 HTML 的逐字节存档。

## 四、怎样导入，哪些情况不能猜测？

文件使用 UTF-8（兼容 BOM），包含表头，允许按标准 CSV 转义的逗号、引号和多行 description。不可用文本行数充当记录数。导入必需列有：`job_id`、`title`、`company`、`location`、`salary`、`experience`、`education`、`url`、`description`、`status`、`collected_at`；其余字段是当前数据集的补充列。

~~~bash
job-rag import data/jobs.csv --source boss --no-index
job-rag worker
~~~

第一条命令导入并登记索引任务，不会调用 Embedding；第二条命令处理索引任务，**若已配置外部 Embedding，可能发生真实模型调用和费用**。完整输入会在写库前校验；同一 CSV 内重复或空 ID、字段列数错配将拒绝导入。空正文可以保存，但不会凭空产生检索内容。

招聘状态不能由采集状态推断：取得正文不等于仍在招，页面失效也不等于招聘已关闭。后续阅读顺序是[预处理](../job_rag/preprocessing/README.md) → [存储](../job_rag/storage/README.md) → [结构化分块](../job_rag/chunking/README.md)。