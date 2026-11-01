"""Build a portable report and blank human-review sheets from recorded MCP output."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path


def build_report(run, output):
    baseline_link = Path(os.path.relpath(Path(__file__).resolve().parents[1] / 'baseline' / 'rag-job-requirements-baseline-v1.md', output)).as_posix()
    def read(name):
        return json.loads((run / name).read_text())

    output.mkdir(parents=True, exist_ok=False)
    summary, broad = read('summary.json'), read('broad_summary.json')
    catalog, acceptance = read('catalog.json'), read('acceptance.json')
    manifest, setup, stats = read('manifest.json'), read('setup.json'), read('stats.json')
    details, full_jobs = read('details.json'), read('full_jobs.json')
    main = {j['key'] for j in read('catalog_jobs.json')}
    preferred = {j['key'] for j in read('preferred_only.json')}
    unresolved = {j['key'] for j in read('unresolved.json')}
    all_keys = {j['key'] for j in full_jobs}
    other = all_keys - main - preferred - unresolved
    assert acceptance['status'] == 'PASS'
    assert len(all_keys) == broad['denominator_jobs']
    assert len(main) == len(details) == summary['denominator_jobs']
    by_key = {j['key']: j for j in details}
    labels = {c['technology']: c['label'] for c in summary['categories']}
    review_rows = []
    for job in full_jobs:
        key = job['key']
        groups = [label for label, keys in [('main', main), ('preferred_without_main', preferred),
                  ('unresolved', unresolved), ('other_sections', other)] if key in keys]
        mentions = by_key.get(key, {}).get('technical_mentions', [])
        review_rows.append({
            'key': key, 'version': job['version'], 'title': job['raw'].get('title', ''),
            'company': job['raw'].get('company', ''), 'url': job['raw'].get('url', ''),
            'job_status': job['job_status'], 'rule_groups': '|'.join(groups),
            'technologies_in_main_scope': '|'.join(sorted({labels[e['technology']] for e in mentions})),
            'description': job['raw']['description'], 'human_rag_in_main': '',
            'human_technologies': '', 'human_baseline_comparison': '', 'reviewer': '', 'review_notes': ''})
    with (output / 'review_jobs.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(review_rows[0]))
        writer.writeheader()
        writer.writerows(review_rows)
    fields = ['key', 'version', 'evidence_kind', 'technology', 'section_type', 'requirement_level',
              'alternative', 'needs_review', 'verified', 'source_start', 'source_end', 'match_start',
              'match_end', 'matched_text', 'text', 'human_mention_correct', 'human_requirement_level',
              'human_direct_rag_relation', 'reviewer', 'review_notes']
    evidence_rows = []
    for job in details:
        for kind, items in [('technology', job['technical_mentions']), ('rag_match', job['match_evidence'])]:
            for evidence in items:
                row = {field: evidence.get(field, '') for field in fields}
                row.update(key=job['key'], version=job['version'], evidence_kind=kind)
                evidence_rows.append(row)
    assert len(evidence_rows) == acceptance['evidence_spans_checked']
    with (output / 'review_evidence.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(evidence_rows)
    metrics = {'acceptance': acceptance, 'setup': setup, 'stats': stats,
               'main_summary': summary, 'broad_summary': broad,
               'independent_rag': read('independent_rag.json')['matched_jobs'],
               'partition': {'main': len(main), 'unresolved': len(unresolved),
                             'preferred_without_main_or_unresolved': len(preferred - unresolved),
                             'other_sections': len(other)},
               'preferred_unresolved_overlap': len(preferred & unresolved),
               'human_review_completed': False}
    for name, obj in [('metrics.json', metrics), ('manifest.json', manifest), ('execution-trace.json', read('trace.json'))]:
        (output / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    n = len(main)
    report = [f'''# Job-RAG RAG 岗位技术要求：全流程实跑报告

运行编号：`{run.name}`。完成时间：{acceptance['completed_at']}。原始问题：统计岗位职责或任职要求出现 RAG 的岗位中，相关的技术要求是什么？

本轮使用所提供的 `jobs-20261023.csv`，经 Job-RAG 导入、规范化、分块索引、真实 MCP/API 查询、全量枚举、技术提及汇总和全文证据校验形成结果。报告根据保存的工具输出整理；未将整份 CSV 直接交给生成模型重新分析，也未使用参考回答的数字生成统计。参考回答仅用于说明可比性。

**主要发现：**全描述口径命中 {len(all_keys)} 条；职责/任职要求章节规则命中 **{n} 条**。主样本常见技术组合包括 Agent/工具调用、Python、Prompt、后端集成和 RAG 框架；直接涉及 RAG 链路的提及包括向量检索、文档处理、Embedding、检索优化及评测。它们是 JD 技术提及，不能全部解释为必备技能或直接用于 RAG 的要求。

## 1. 数据、筛选口径与覆盖

| 项目 | 本轮结果 |
|---|---:|
| 导入岗位 | {stats['total']} |
| 有描述 / 缺描述 | {stats['descriptions']['present']} / {stats['descriptions']['missing']} |
| 独立 RAG，全描述 ASCII 边界匹配 | {metrics['independent_rag']} |
| 扩展 RAG / GraphRAG / RAGFlow，全描述 | {len(all_keys)} |
| 职责/任职要求主样本 | {n} |
| 主样本外，未识别章节出现 RAG | {len(unresolved)} |
| 主样本外，独立加分章节出现 RAG | {len(preferred)} |
| 上述未识别章节与加分章节交集 | {len(preferred & unresolved)} |
| 主样本中含有未识别文本的岗位 | {summary['technical_scope_unknown_jobs']} |
| 导入 / 索引失败 | 0 / {setup['index']['failed']} |

只匹配 `description`，不使用标题或采集关键词确定 RAG 样本。忽略大小写，`ascii_token` 表示前后不能为 ASCII 字母、数字或下划线，因此支持紧邻中文的 RAG；显式将 GraphRAG、RAGFlow 列为 RAG 别名。按 `source:job_id` 去重，同类别每岗计一次，跨类别可重叠。主样本的技术统计也仅检查职责/任职要求章节，不纳入独立加分项、公司介绍、福利及 unknown 段落；主章节句内的“优先”仍保留规则标签。

为冻结历史数据，查询使用 `include_closed=true`；本次 {stats['total']} 条均为 `unknown`，不表示已确认在招。未运行近重复内容合并或招聘有效性核验。章节及技术分类均为规则输出，没有完成逐岗语义标注。

互斥分解是：主样本 {n} + 未识别待判定 {len(unresolved)} + 排除这两组后加分项 {len(preferred - unresolved)} + 其他章节 {len(other)} = {len(all_keys)}。上表的 {len(preferred)} 与 {len(unresolved)} 不能直接相加。

主样本中 {summary['technical_scope_unknown_jobs']} 份 JD 仍有 unknown 文本，故即使 RAG 已成功归入主体，也可能遗漏未知段落的技术要求。`count_complete=true` 仅表示按规则全量扫描完成，`semantic_count_complete=false`。

## 2. 技术提及统计

分母为 {n} 份 JD。括号内技术由固定词表合并，类别可重叠。右列提供同一词表在全描述扩展样本 {len(all_keys)} 份中的计数，供判断口径影响；它不是首轮参考报告的自动重算。

| 技术类别 | 主样本岗位数 | 主样本占比 | 全描述扩展计数 |
|---|---:|---:|---:|''']
    broad_by = {c['technology']: c for c in broad['categories']}
    for c in summary['categories']:
        report.append(f"| {c['label']} | {c['job_count']} | {c['fraction']:.1%} | {broad_by[c['technology']]['job_count']} |")
    report.append('''
从这些提及可以归纳出三个方向：一是 Agent 与业务应用集成，二是文档—向量—检索—评测链路，三是后端与部署工程。这是基于类别及下文证据的解释，不是已验证的岗位能力分层。向量检索类别同时包含向量数据库及具体产品；检索优化合并混合检索、BM25、重排和召回指标；评测合并了广义模型评测与幻觉治理。因此本轮不能给出每个具体产品或 Rerank、Chunking 的独立排行榜，也不能把合并类别直接与基准单项比较。

## 3. 条件性质及原文证据

下表为规则分组。`required` 只反映明确触发词；`unspecified` 不等于“不要求”；同一岗位可跨条件组出现，不能相加。所有证据的 `verified=false`，代表尚未人工核验。

| 类别 | 职责 | 明确必备触发词 | 优先 | 否定 | 混合 | 未明确 |
|---|---:|---:|---:|---:|---:|---:|''')
    for c in summary['categories']:
        counts = c['condition_job_counts']
        values = [str(counts.get(x, 0)) for x in ['responsibility', 'required', 'preferred', 'not_required', 'mixed', 'unspecified']]
        report.append('| ' + c['label'] + ' | ' + ' | '.join(values) + ' |')
    report.append('\n以下按工具返回顺序展示可追溯案例，非随机抽样，不用于估计准确率。字符区间采用 Python 字符索引，左闭右开。')
    samples = ['agent_workflow_tools', 'vector_retrieval', 'embedding', 'evaluation', 'retrieval_optimization']
    full_by = {j['key']: j for j in full_jobs}
    for tech in samples:
        category = next(c for c in summary['categories'] if c['technology'] == tech)
        e = category['evidence_samples'][0]
        j = full_by[e['key']]
        title = j['raw'].get('title', e['key'])
        url = j['raw'].get('url', '')
        report.append(f"\n- **{category['label']}**：[{title}]({url})，`{e['key']}`，版本 {j['version']}，`{e['section_type']}`，原文 [{e['source_start']}, {e['source_end']})。\n\n  > " + e['text'].strip().replace('\n', ' '))
    report.append(f'''
**已发现的规则风险：**“检索优化”示例命中“根据业务场景选择适配模型并调优指标（准确率、召回率、推理速度）”，这段证据谈的是模型指标，不能证明它是 RAG 检索优化。类似地，文档处理类包含“数据治理”，可能属于宽泛交付职责；Python 出现在“Python 或 TypeScript 至少一门精通”时，也不能判成 Python 单项必备。人工需要逐条判断技术提及是否正确、条件性质及是否直接用于 RAG。

## 4. 与首轮参考回答的对比边界

首轮参考文件为 [rag-job-requirements-baseline-v1.md]({baseline_link})，它不是逐条人工 gold。本轮没有覆盖或修订该文件。

| 对比项目 | 首轮参考 | 本轮 | 解读 |
|---|---:|---:|---|
| 总岗位 | 593 | {stats['total']} | 数量一致；首轮未给文件哈希，不能仅凭此证明版本一致 |
| 全描述独立 RAG | 424 | {metrics['independent_rag']} | 数量一致 |
| 全描述扩展 RAG | 426 | {len(all_keys)} | 数量一致，不证明逐岗集合相同 |
| 职责/任职要求主样本 | 附注提及另一报告的 392 | {n} | 前者不是 V1 主口径；需人工检查章节差异，不能直接当作漏召回数 |
| Python：全描述扩展样本 | 280 | {broad_by['python']['job_count']} | 同名项目数值一致，首轮无逐条证据清单 |
| Embedding/向量化：全描述 | 64 | {broad_by['embedding']['job_count']} | 数值一致，不证明词表或集合完全一致 |
| MCP：全描述 | 115 | {broad_by['mcp']['job_count']} | 数值一致 |
| 技术分类粒度 | 多个细项 | 固定 15 组 | 其余合并项不直接计算差值或正确率 |

本轮支持人工检查覆盖范围、归类和证据，不支持发布准确率/召回率、优于首轮模型的结论，或将规则统计说成全量语义判断。未识别段落可能产生漏项，固定词表也可能遗漏同义表达或新增技术。没有真实标签时不推算误差。

## 5. 实际使用的能力与对应产物

| 能力 | 实际执行及产物 |
|---|---|
| CSV 导入、规范化与版本化 | 新建隔离 SQLite，{setup['import']['created']} 条创建；`setup.json`、`analysis.db` |
| 章节分块与词法索引 | `section_typed`，预算 {setup['chunk_size']} 字符，{setup['index']['indexed']} 条索引完成；`setup.json` |
| MCP 工具发现与状态检查 | 真实 Streamable HTTP；6 个工具全部调用；`stats.json`、`execution-trace.json` |
| 全量目录查询与快照绑定 | 全描述及主体分页；每页绑定 snapshot，批量全文绑定 corpus；`catalog*.json`、`broad*.json` |
| 技术提及及条件规则汇总 | `{summary['vocabulary_version']}` / `{summary['condition_rule_version']}`；`summary.json`、`details.json` |
| 全文读取与证据校验 | 批读 {len(full_jobs)} 份匹配全文；逐一验证 {acceptance['evidence_spans_checked']} 条主样本返回证据；`full_jobs.json`、`acceptance.json` |
| 候选检索与详情复核 | 另执行“企业RAG知识库建设”，限定广州、月薪下限 20,000 元，使用改写及 BM25/RRF；`candidates.json`，不参与总体统计 |
| 重排降级 | 显式请求 rerank，返回 `not_configured`；只验证降级，没有完成模型重排 |
| 报告整理及人工复核交接 | 根据落盘结果生成本报告、{len(review_rows)} 行逐岗表和 {len(evidence_rows)} 行证据表，未填人工结论 |

Embedding 与 Job-RAG 内置 Chat 模型均关闭，付费模型请求为 0。没有执行真实向量召回、模型重排或 Job-RAG 内置答案生成；自然语言分析由当前 Codex 根据已保存结果整理。因此这是当前配置下的规则分析及词法检索全流程，不是所有可选模型组件均启用的端到端 RAG 模型质量评测。候选检索仅是补充能力验证，不用 Top-K 结果推算总体。

## 6. 验证结果和人工复核方法

实跑 `PASS` 的含义：导入/索引无失败，真实 MCP 调用成功，全量分页无重复、无遗漏，类别岗位数与明细重新聚合一致，主样本返回证据与批量获取的完整原文字符位置一致，结束时快照仍有效。证据校验范围是接口实际返回的主样本证据；它不证明接口发现了原文的全部提及。`match_evidence` 每岗有返回上限，可能有截断标记，逐岗表保留全文以供补查。

人工先填写 `review_jobs.csv` 的 `human_rag_in_main`，优先查看 `unresolved`、`preferred_without_main` 和 `other_sections`，随后审核主样本；再填写 `review_evidence.csv` 的提及正确性、条件性质和直接 RAG 关系。所有 `human_*` 与 `reviewer` 字段留空。逐岗表包含每个全描述匹配岗位的完整 JD，可补充规则漏提取的技术。主样本外的岗位未生成技术证据，不能把其技术列为空解释为无技能要求。

建议先独立阅读证据形成判断，再比较首轮报告；不以首轮数字为目标回填。记录争议原文、最终口径、审核人及修订原因。当前没有人工标签，所以不能执行可信的自动质量评分。

## 7. 产物清单及复现

本目录交付：`report.md`（本报告）、`metrics.json`（统计及校验结果）、`review_jobs.csv`（逐岗全文与空白审核栏）、`review_evidence.csv`（规则证据与空白审核栏）、`execution-trace.json`（每次调用参数、耗时和 request_id）、`manifest.json`（数据及实现哈希）、`artifacts.json`（交付文件 SHA-256）。CSV 使用 UTF-8 BOM，可用表格软件打开。

完整运行归档在 `{run}`：隔离数据库、导入索引信息、44 次调用各自的参数及响应 `calls/`、全量目录、汇总、明细、全文、待判定及加分项、候选结果。该目录受 Git 忽略，应与报告一起另行归档，不能假设提交代码就已保存数据库和原始响应。首次受限沙箱运行仅完成导入索引，在 socket 创建时失败，位于 `runtime/experiments/rag-tech-20261101`，未计入本次成功运行。

源 CSV SHA-256：`{manifest['csv_sha256']}`。语料 ID：`{catalog['corpus_id']}`。章节规则：`{catalog['section_rule_version']}`。Git HEAD 与逐文件实现指纹见 manifest；工作区有未提交变更，所以 HEAD 本身不能唯一代表本轮实现。完整运行流程独立于已删除的旧任务实验模块。

从仓库根目录复现，输出目录必须尚不存在；环境须允许本机回环 socket：

```bash
.venv/bin/python experiments/rag_tech_requirements/scripts/run_pipeline.py --output runtime/experiments/rag-tech-new
.venv/bin/python experiments/rag_tech_requirements/scripts/build_report.py --run runtime/experiments/rag-tech-new --output experiments/rag_tech_requirements/results/new/rules
```

本轮相关验证命令：

```bash
.venv/bin/pytest -q tests/test_ingest.py tests/test_chunking.py tests/test_catalog.py tests/test_section_analysis.py tests/test_candidates.py tests/test_candidate_rerank.py
```

实际结果：**91 passed in 4.70s**。这是本次人工执行的验证记录，不是报告生成程序自动运行的测试；复现实验后需重新记录。生产业务代码未修改，原有删除项及基准保留原状。
''')
    (output / 'report.md').write_text('\n'.join(report))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
    hashes['report_builder_source'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output / 'artifacts.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': str(output / 'report.md'), 'jobs': len(review_rows), 'evidence': len(evidence_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build_report(args.run, args.output)
