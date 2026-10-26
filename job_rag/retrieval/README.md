# 候选检索、证据与回答

本目录提供有排名、允许截断的候选召回，不承担全库精确计数。

| 文件 | 职责 |
|---|---|
| `search.py` | `SearchRequest`、保守查询条件识别、分词/BM25、可选向量、Chunk 级融合、岗位聚合及证据上下文 |
| `candidates.py` | 原问题加按需改写的多查询检索、岗位级 RRF、去重及版本/状态复核 |
| `answer.py` | 可核对的来源列表、可选 Chat、引用编号检查与生成后数据复核 |

## 普通检索流程

1. `resolve_filters()` 仅保守识别明确城市、薪资或经验表达；显式参数优先。公共条件定义与 `matches()` 来自 `querying/filters.py`。
2. 原文和标准字段经过硬过滤；只有当前版本且索引签名匹配的岗位参与检索。过滤仍在 Python 应用层执行。
3. `tokens()` 用英文技术词正则和中文字符二元组；`bm25()` 对正文块评分。
4. 配置模型后调用 `providers.client.embed()`：PostgreSQL 用 pgvector 精确余弦距离，SQLite 在 Python 计算；失败降级为关键词召回，没有 ANN 索引。
5. 各通道前100个 Chunk 参加 RRF，随后按岗位聚合。每岗最多2个命中证据块，并补充最多约3600字符的要求/加分章节上下文。
6. `answer()` 组织来源列表；仅在请求 `generate=true` 且已配置 Chat 时生成回答，并执行基础引用编号检查。生成后复核版本及状态，变化时拦截结果。

多查询层最多额外4条改写，每条最多30个岗位，再按 `source:job_id` 累加 RRF 贡献，最终 `candidate_limit` 最大60。RRF 使用排名贡献 `1/(60+rank)`，不把 BM25 与余弦原分数直接相加。

`total_matched`、`total_candidates` 是有截断的检索数量，不是全库符合要求的数量；`fusion_score` 不是语义满足概率。弱偏好不能放进字面AND的 `skills`。

## 回答与语义理解的边界

调用方 Agent 可以读证据、补检索、获取完整 JD 后重排；这不同于网页/API 的 Chat 路径，也不意味着已经运行专用 Reranker。片段未出现某条件不能证明全文没有，条件标签也不是核验事实。

岗位公共输出由 `storage/serialization.py` 提供。完整读取、精确字面计数见[querying](../querying/README.md)。线上 Chunk 融合后聚合与离线同岗向量取最大值不是同一流程，实验说明见[experiments](../experiments/README.md)。
