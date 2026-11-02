# 招聘数据为什么要保留原文？——Job-RAG 的输入与证据基础

Job-RAG 不直接把采集到的招聘信息交给模型“读完记住”。如果模型回答“广州有 20 个要求 vLLM 的岗位”，我们必须进一步追问：原始 JD 是否真的提到 vLLM？它是在岗位职责还是公司介绍中出现？采集于哪一天？这个岗位是否还在招？

这些问题无法仅靠一段模型回答复原，因此 `data/jobs.csv` 的第一责任是**保存外部已获得的招聘文本和来源线索**，让每个后续判断有机会回到原始输入。

## 一、为什么把爬虫和知识库分开？

网页采集有验证码、页面结构、反爬和登录状态等问题，知识库则要处理版本、筛选、检索和证据。如果抓取失败就意味着数据库删除对应岗位，那么“没采到”会被错误解释为“已关闭”；如果改变网页解析规则就顺便改变索引，又很难分清数据变化和算法变化。

项目因此只接受外部流程整理好的 CSV。采集负责“取得什么文字”，Job-RAG 负责“怎样可靠保存、加工和查询”。新 CSV 未包含某岗位，不自动删除或将其关闭。

~~~text
外部采集 → 标准 CSV → 预处理/入库 → 原文与版本 → 分块索引 → 检索/分析
~~~

## 二、为什么一份岗位要保留这些字段？

截至 2026-11-02 合并基线，主表含 **2,546** 个不同 `job_id`，其中 **2,545** 条 `description` 非空；2026-11-02 起主表由 12 个采集字段扩展为 13 列（新增 `analysis`），并调整部分岗位管理状态。当前实际数字请运行 `python scripts/report_dataset.py` 获取。最重要的不是列数，而是**字段扮演不同的证据角色**。

假设一条招聘标题为“AI 平台工程师”，薪资“20–35K”，正文含“vLLM 经验优先”。`title/company/location/salary/experience/education` 描述招聘方展示的基本属性；`description` 承载实际职责、必备条件和加分语境；`job_id` 是以后识别同一来源岗位更新的关键；`url` 与 `collected_at` 让人能追溯出处和采集日期。

采集字段 `keywords/collected_at` 记录关键词来源和采集时间，不等于岗位的真实技术要求。主表 `status` 是人工维护的管理状态：2026-10-31 已撤销“未被下一次搜索命中就判定下线”的规则；2026-11-02 根据投递记录和人工核验修正部分状态。此后合并不会自动将旧岗位标成下线，也不会覆盖已经维护的状态；新岗位默认 `招聘中` 仅是台账初始值，**不代表网站实时核验**。数据库 `job_status` 与 CSV 管理字段独立，导入时不自动映射；详见 [data_merge](data_merge/README.md)。

`analysis` 是供上层 [apply-flow](../apply-flow/README.md) 使用的工作内容解读，不是网站原始 JD。合并器保留该列及未来新增的管理字段，采集数据不可覆盖人工结论。已删除的 `first_keyword/keyword_count/is_guangzhou/address` 不应恢复；只改变 `status/keywords/collected_at/analysis` 等非内容字段，不会触发知识库的内容版本递增或重复 Embedding。

## 三、为什么不在这里直接清洗、摘要或生成 Embedding？

如果导入前先把“vLLM 经验优先”摘要为“vLLM 技术能力”，那么“优先”这个关键约束就丢失了。后来即使用更好的模型重分析，也不知道错误来源于招聘原文还是预处理摘要。

因此这里保留外部提供的 `description` 文字，不进行无依据的改写；[预处理](../job_rag/preprocessing/README.md)额外生成 `normalized`，[分块](../job_rag/chunking/README.md)额外生成索引文本和来源偏移。后续模型理解错了，可以重算派生数据而不覆盖原文。这里保存的是 CSV 中的正文，不是网页 HTML 的字节级存档。

## 四、怎样导入及识别缺失？

输入要求 UTF-8（兼容 BOM）与标准 CSV 转义；带换行、引号的 JD 仍是一条记录，不能拿文件行数当岗位数。11 个列名必须存在：`job_id/title/company/location/salary/experience/education/url/description/status/collected_at`。同批数据不能重复 `job_id`，但正文可以为空；空正文不会被编造为“暂无要求”。

~~~bash
job-rag import data/jobs.csv --source boss --no-index
job-rag worker
~~~

第一条只导入并登记索引任务；第二条构建索引，配置外部 Embedding 时会发生模型请求。新建岗位状态默认为 `unknown`：采集成功不能证明在招；网页打不开也不能自动判定关闭。

这个目录提供的是可信的**输入起点**，不是招聘市场总体样本，更不是答案库。接下来应看[预处理](../job_rag/preprocessing/README.md)如何让原文具备确定性的筛选字段，以及[存储](../job_rag/storage/README.md)如何保留版本和状态。
## 五、采集 CSV 如何合并到 jobs.csv？

按日期将新文件保存至 `collections/YYYY-MM-DD/`，其中只保留岗位采集 CSV；公司补充信息单独存于 `company/company_info.csv`。通过 [data_merge](data_merge/README.md) 的脚本按 `job_id` 合并至唯一主表。2026-10-31 的广州/深圳 AI应用开发批次新增 **472** 条；2026-11-01 的广州/深圳大模型应用开发批次新增 **315** 条；2026-11-02 的广州 5 关键词批次新增 **435** 条，主表合计 **2,546** 条。合并不会自动更新运行时数据库和索引，也不会覆盖主表的人工分析与状态字段。
