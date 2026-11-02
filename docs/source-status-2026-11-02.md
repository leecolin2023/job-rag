# Job-RAG 源码能力状态（2026-11-02）

> 检查基准：GitHub `main` 分支当日源码。**这是源码与归档记录检查，不是线上服务器实时监控，也不是一次完整的本地端到端测试。** 历史服务器运行验收仍见 [2026-10-25 快照](current-status.md)。

## 当前系统处理哪几件事？

| 层次 | 当前源码 | 已验证范围和局限 |
|---|---|---|
| 采集 / 合并 | `data/collections/YYYY-MM-DD/` 保存岗位采集；`data/data_merge/merge_jobs.py` 负责增量合并 | 2026-11-01 批次归档为 2,111 条，其中 2,110 条有正文；后续状态及人工分析有变化，不应沿用旧状态总数 |
| 人工管理 | `data/jobs.csv` 增加 `analysis`，人工修改 `status`；合并器保留人工列及人工状态 | 2026-11-02 历史提交说明增加了 11 条分析、更新 80 条状态；实际状态分布应由数据文件统计 |
| 知识库 | `job_rag/preprocessing/storage/chunking/indexing` 提供校验、版本、分块及可重试索引 | CSV 变化不等于运行数据库已同步；`analysis` 与采集元数据不触发正文索引版本 |
| 查询与检索 | `querying` 提供全库字面匹配、分页与 JD 批读；`retrieval` 提供 BM25/可选向量检索、候选融合和可选重排 | 完整字面统计不等于完整语义判定；候选 Top-K 不能代表全库数量 |
| 服务入口 | `interfaces` 提供内部 API、管理 CLI 和六个只读 MCP 工具 | 面向 Agent 以 MCP 为主，不能直接删除支撑 MCP 的 HTTP API 或运维 CLI |
| 模型 | `providers/client.py` 提供 Embedding/Chat，`providers/rerank.py` 支持可选 Rerank | 启用必须配置模型服务并在请求中选择；源码存在并不代表线上正在运行 |
| 实验 | `experiments/rag_tech_requirements` 保留规则及完整模型实验、人工复核表 | 2026-11-01 已归档真实模型报告，但不代表所有人工复核完成；历史检索排名的独立第二轮尚未完成 |
| 投递工作流 | `apply-flow` 负责工作内容理解及人工确认后的沟通，借助外部 `browser-ops` | 不属于知识库核心，外部浏览器操作依赖单独项目；不能因代码提交就推断动作已执行 |

## 怎样获取当前数据数字？

```bash
python scripts/report_dataset.py
python -m unittest discover -s data/data_merge -p 'test_merge_jobs.py'
pytest -q
```

统计脚本只读 `data/jobs.csv`，报告总行数、不同 `job_id`、列、正文覆盖、人工分析覆盖、状态分布和最新采集日期；它不查询 BOSS 网站，也不表示岗位实时在招。

## 修改及部署边界

- `data/jobs.csv` 是 Git 中的采集+人工管理台账；数据库内的 `job_status` 是另一个状态字段，导入不会自动映射。
- `analysis` 不属于岗位原始职责。合并必须保留它，索引仍只依据明确的正文内容字段。
- `job_rag` 的八个业务模块保持原状。历史评测报告的冻结数据、指标与 manifest 不重写。
- 需要在目标环境重新安装包/构建镜像、检查数据库与索引签名后，才能把新源码应用于线上。此次文档整理和数据脚本修复本身不执行远程部署。
