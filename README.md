# Job-RAG

AI 招聘岗位知识库（基础数据准备阶段）。

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

1. `jobs.csv` 是唯一事实来源，无需维护分拆的有/无详情文件或独立的 `documents` 目录。
2. 以 `job_id` 做增量更新（upsert）；不使用 CSV 行号作为岗位主键。
3. 生成 Embedding 前只选择 `description` 非空的岗位。文本由程序动态组装为检索 Document，不直接修改原始描述。
4. 地区、薪资、经验等字段可用于结构化筛选，岗位职责与技术要求用于语义检索。
5. 当前只有基础数据集，尚未生成向量库或检索服务。

## 数据与隐私

此仓库为公开仓库。CSV 不包含专门的招聘者身份/活跃信息字段与企业工商登记原文。请勿提交 API Key、个人简历或其他私有资料。原始 Excel 建议妥善保存于非公开位置。
