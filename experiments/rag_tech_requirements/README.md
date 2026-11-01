# RAG 岗位技术要求实验

本实验回答：**岗位职责或任职要求出现 RAG 的岗位中，相关技术要求是什么？** 使用冻结的岗位 CSV，先通过 Job-RAG 全量目录和技术统计获取计数，再执行真实 Embedding、混合召回、模型重排及内置生成，将报告与首轮参考回答交给人工比较。

优先阅读 [2026-11-01 完整模型报告](results/2026-11-01/models/report.md)。其中记录使用的能力、模型调用、产物、失败续跑及发现的生成错误。[规则路径报告](results/2026-11-01/rules/report.md)保留作对照，不代表完整模型链路。

## 目录

```text
rag_tech_requirements/
├── README.md
├── data/
│   └── jobs-20261023.csv                 # 冻结的593条岗位输入
├── baseline/
│   └── rag-job-requirements-baseline-v1.md # 首轮参考回答，未经逐岗人工核验
├── scripts/
│   ├── run_pipeline.py                  # 全量MCP规则统计与证据校验
│   ├── build_report.py                  # 打包规则报告与人工表
│   ├── run_models.py                    # 真实模型链路执行
│   └── build_model_report.py            # 合并统计、模型输出与人工表
└── results/
    ├── README.md                        # 结果归档及历史路径说明
    └── 2026-11-01/
        ├── rules/                       # 规则路径报告、计数、证据、调用追踪
        └── models/                      # 完整模型报告、原始回答、调用及复核表
```

完整数据库、向量和逐次 MCP 原始请求/响应保存在仓库根目录的 `runtime/experiments/`，受 Git 忽略，需要另行归档。`results/` 保存可携带的报告与审核材料。

## 已有结果与人工审核入口

| 内容 | 入口 |
|---|---|
| 完整模型报告（主交付） | [models/report.md](results/2026-11-01/models/report.md) |
| 全库规则统计及方法限制 | [rules/report.md](results/2026-11-01/rules/report.md) |
| 首轮参考回答 | [baseline](baseline/rag-job-requirements-baseline-v1.md) |
| 426份完整JD及空白人工结论栏 | [review_jobs.csv](results/2026-11-01/models/review_jobs.csv) |
| 5,019条规则证据及空白判定栏 | [review_evidence.csv](results/2026-11-01/models/review_evidence.csv) |
| 三轮模型原始回答及空白审核栏 | [review_generation.csv](results/2026-11-01/models/review_generation.csv) |
| 模型回答、来源与证据 | [generated_answers.json](results/2026-11-01/models/generated_answers.json) |
| 真实模型响应、用量及请求哈希 | [provider_calls.jsonl](results/2026-11-01/models/provider_calls.jsonl) |

本轮导入593条岗位，真实索引生成2,443个1,024维向量；三轮回答均完成混合召回、重排与内置生成。使用 `qwen3.7-text-embedding-flash`、`qwen3.7-text-rerank`、`qwen-plus`，正式运行记录604次成功响应，另保留一次生成失败续跑记录。统计层此前完成44次真实MCP调用，模型层走生产函数及真实HTTPS，两类调用分别记录。

全描述扩展匹配426条，职责/任职要求章节规则匹配384条，另有未知章节及加分项需要人工核对。计数是规则下的技术提及；模型段落是有限检索来源的分析，不能用Top-K推算全库频次。所有人工结论栏留空，当前没有人工gold或可信的准确率结论。先独立审核原文及条件关系，再与首轮参考比较。

## 复现完整流程

从仓库根目录执行，使用已有 `.venv`。规则路径需要允许本机回环socket；真实模型路径读取根目录 `.env.experiments` 中已有的 `BAILIAN_API_HOST`、`BAILIAN_API_KEY`、`BAILIAN_EMBEDDING_MODEL`、`BAILIAN_EMBEDDING_DIMENSIONS` 和 `BAILIAN_RERANK_MODEL`，生成模型使用已验证的 `qwen-plus`。后两步涉及真实模型调用及账户费用。

先运行全量规则统计并生成报告，再运行模型链路并打包。示例中 `new` 是新实验的目录名；正式归档建议改为日期或明确的实验编号：

```bash
# 1. 导入、分块索引、真实MCP全量枚举、技术汇总、批读全文及证据位置校验
.venv/bin/python experiments/rag_tech_requirements/scripts/run_pipeline.py \
  --output runtime/experiments/rag-tech-rules-new

# 2. 导出规则报告、统计和人工表
.venv/bin/python experiments/rag_tech_requirements/scripts/build_report.py \
  --run runtime/experiments/rag-tech-rules-new \
  --output experiments/rag_tech_requirements/results/new/rules

# 3. 真实文档Embedding → 混合召回 → 完整JD重排 → 内置Chat生成
.venv/bin/python experiments/rag_tech_requirements/scripts/run_models.py \
  --output runtime/experiments/rag-tech-models-new

# 4. 校验两条路径使用相同CSV，合并统计、原始回答和人工复核材料
.venv/bin/python experiments/rag_tech_requirements/scripts/build_model_report.py \
  --run runtime/experiments/rag-tech-models-new \
  --rule-report experiments/rag_tech_requirements/results/new/rules \
  --output experiments/rag_tech_requirements/results/new/models
```

两个执行脚本默认读取 `data/jobs-20261023.csv`，不读首轮参考报告生成统计。`run_pipeline.py` 可用 `--csv` 指定规则层输入；模型执行脚本仍读取上述固定文件，不能只改变规则层输入就声称完成同一数据的模型实验。打包时会核对源CSV哈希。

规则执行和报告打包要求输出目录尚不存在。模型执行允许在同一目录续跑，复用完成的索引及成功回答，保留失败尝试和先前manifest；数据、实现或模型配置改变时应另起实验目录。模型路径出现降级会保存结果并报错，不计为完成。生成超时配置为180秒。

## 产物说明

| 产物 | 用途 |
|---|---|
| `report.md` | 阅读结论、方法、能力使用、产物及局限 |
| `metrics.json` | 程序统计、运行状态、规则及模型计数 |
| `review_*.csv` | 人工核对岗位、证据及生成结论；UTF-8 BOM编码 |
| `generated_answers.json` | 模型回答与各自来源，引用编号按轮解释 |
| `execution-trace.json` / `provider_calls.jsonl` | 分别追踪MCP与真实模型调用 |
| `*manifest*.json` | 输入、运行实现及各次尝试的指纹 |
| `failed-attempts.json` | 未被计作成功的生成尝试 |
| `artifacts.json` | 归档文件的SHA-256 |

`models/` 中复制逐岗及逐证据表，便于将整个模型报告目录独立交给审核人；`rules/` 中保留原版，避免结果依赖跨目录读取。

本次整理仅移动文件、调整路径及文档；历史数据、模型输出与manifest内容保留。报告中的复现命令和相对链接已更新，报告文件哈希同步更新；历史manifest内的旧路径仍表示当时的运行位置，详情见 [结果归档说明](results/README.md)。旧 `task_runner/task_eval/task_review` 实现已不在当前工作区，本任务使用这里列出的四个脚本，不恢复旧任务代码。
