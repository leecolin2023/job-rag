# 实验结果归档

按实验日期或编号分组，每组使用 `rules/` 和 `models/` 区分两条执行路径。可直接交付整个 `models/` 目录，其中包含统计、模型回答、调用记录和人工复核表。

| 归档 | 规则路径 | 完整模型路径 |
|---|---|---|
| 2026-11-01 | [报告](2026-11-01/rules/report.md) | [主报告](2026-11-01/models/report.md) |

本次整理迁移关系：

| 原位置（相对实验根目录） | 现位置 |
|---|---|
| `results-20261101/` | `results/2026-11-01/rules/` |
| `results-real-20261101/` | `results/2026-11-01/models/` |
| `jobs-20261023.csv` | `data/jobs-20261023.csv` |
| `rag-job-requirements-baseline-v1.md` | `baseline/rag-job-requirements-baseline-v1.md` |
| 根目录四个执行/打包脚本 | `scripts/` 下同名文件 |
| `PIPELINE.md` | 合并更新为根目录 `README.md` |

历史manifest、调用记录、统计、模型原始回答和审核表未重写；manifest中的旧绝对路径与实现哈希描述的是当时的运行环境，不能要求它们与整理后的脚本路径或源码哈希相同。`artifacts.json` 中的 `report_builder_source` 也是历史构建器源码指纹，不是归档文件名。

报告中的相对链接和复现命令已随迁移更新，`artifacts.json` 中对应的 `report.md` 哈希同步更新。其余归档文件哈希保持原值。整理过程未重新运行模型，未改写实验数字或填入人工标签。

完整数据库、向量及每次MCP原始请求/响应仍在 `runtime/experiments/`，其位置未变，且受Git忽略。新的执行步骤、配置要求与人工审核顺序以[实验README](../README.md)为准。
