"""Package real-model output with full-corpus rule statistics for human review."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--rule-report',type=Path,default=Path(__file__).resolve().parents[1] / 'results' / '2026-11-01' / 'rules')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def read(p): return json.loads(p.read_text())
    def write(name,obj): (args.output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    completion=read(args.run/'completion.json')
    assert completion['status']=='PASS'
    manifest=read(args.run/'manifest.json')
    rules=read(args.rule_report/'metrics.json')
    rule_manifest=read(args.rule_report/'manifest.json')
    assert manifest['csv_sha256']==rule_manifest['csv_sha256']
    stats=read(args.run/'stats.json')
    assert stats['indexed']==stats['total']==593 and stats['vectors']==stats['chunks']>0
    calls=[json.loads(line) for line in (args.run/'provider_calls.jsonl').read_text().splitlines()]
    assert all(c['status']==200 for c in calls)
    model_calls=Counter(c['model'] for c in calls)
    text_types=Counter()
    for c in calls:
        if 'text_type' in c: text_types[c['text_type']]+=c['inputs']
    results={name:read(args.run/f'{name}.json') for name in ['overview','retrieval','engineering']}
    for r in results.values():
        assert r['mode']=='hybrid' and r['answer_mode']=='llm' and r['rerank']['applied']
        citations=[int(x) for x in re.findall(r'\[(\d+)\]',r['answer'])]
        assert citations and all(1<=x<=len(r['results']) for x in citations)
    args.output.mkdir(parents=True,exist_ok=False)
    for name in ['review_jobs.csv','review_evidence.csv']:
        shutil.copyfile(args.rule_report/name,args.output/name)
    shutil.copyfile(args.run/'provider_calls.jsonl',args.output/'provider_calls.jsonl')
    write('model-manifest.json',manifest)
    write('attempt-manifests.json',{p.name:read(p) for p in sorted(args.run.glob('manifest-attempt-*.json'))})
    write('failed-attempts.json',{p.name:read(p) for p in sorted(args.run.glob('*-attempt-*.json')) if not p.name.startswith('manifest-')})
    write('rule-manifest.json',rule_manifest)
    write('metrics.json',{'models':{'completion':completion,'stats':stats,'model_call_counts':dict(model_calls),
         'embedding_inputs_by_type':dict(text_types)},'full_corpus_rules':rules,
         'same_csv_hash_confirmed':True,'human_review_completed':False})
    write('generated_answers.json',results)
    review=[]
    for name,r in results.items():
        review.append({'analysis':name,'answer':r['answer'],'source_keys':'|'.join(j['key'] for j in r['results']),
          'human_factual_accuracy':'','human_citation_support':'','human_qualification_relations':'',
          'human_sample_scope':'','human_baseline_comparison':'','reviewer':'','notes':''})
    with (args.output/'review_generation.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(review[0]));w.writeheader();w.writerows(review)
    categories=rules['main_summary']['categories']
    n=rules['main_summary']['denominator_jobs']
    text=[f'''# Job-RAG 完整模型链路实跑：RAG 岗位技术要求报告

运行：`{args.run.name}`；完成：{completion['completed_at']}。本报告替代此前仅规则/词法路径报告作为本次全流程验证的主交付；原报告保留作对照。

## 1. 执行结果及结论范围

**真实 Embedding、混合召回、模型重排和 Job-RAG 内置生成均已执行成功，无降级结果计为成功。** 使用原有百炼账户配置，在隔离库导入 593 条岗位，生产索引 worker 完成真实文档向量生成。三轮分析分别经过生产 `answer()` 的同一条链：query Embedding → BM25/向量混合召回与 RRF → 完整 JD 模型重排 → 将重排后的证据送入内置 Chat 生成 → 引用编号校验和来源状态复核。

全库精确计数仍由 Job-RAG 全量目录及技术统计接口承担，不用向量 Top-K 推算总数。它们使用上次已保存的真实 MCP 全量执行结果，经源 CSV SHA-256 核对，与本次模型运行是同一输入文件。模型段落仅解释检索来源中的要求，不冒充全部岗位的逐岗语义结论。

| 模型环节 | 请求模型名称 | 实跑证据 |
|---|---|---|
| 文档及查询 Embedding | `{manifest['embedding_model']}` | {stats['vectors']} 个真实 {manifest['embedding_dimensions']} 维向量，文档输入 {text_types['document']} 条、查询输入 {text_types['query']} 条 |
| 岗位重排 | `{manifest['rerank_model']}` | 三轮 `rerank.applied=true`，完整标题及 JD，不截断原文 |
| 内置生成 | `{manifest['generation_model']}` | 三轮 `answer_mode=llm`，生成的引用编号与各轮重排后来源对应 |

模型名为请求别名，不保证供应商后台版本永远固定。实际调用记录见 `provider_calls.jsonl`，包含模型名、响应 ID、用量、耗时、状态及请求哈希，不含密钥。探针为独立的 3 次模型调用，不计入下表的正式运行统计。正式运行曾有一次生成在原60秒限制下未返回可接受结果；失败回答保存在 `failed-attempts.json`，它之前成功的查询向量和重排请求仍包含在下表。续跑将生成超时设为180秒，复用已完成索引和总览回答，并重新运行失败的检索链路分析。下表只统计有成功HTTP响应的请求，未返回响应的生成尝试不包含在其中，实际计费须核对供应商记录。

| 正式运行模型 | 成功响应数 |
|---|---:|''']
    for model,count in model_calls.items():text.append(f'| {model} | {count} |')
    text.append(f'''
文档输入数可能高于岗位数，因为一份 JD 有多个 Chunk；索引 worker 按岗位执行，所以请求数也不等于向量数。调用费用以供应商账单为准，本报告不拿未知价格或估计 token 推算实际扣费。

## 2. 全库技术统计：事实层

同一 CSV 中有 593 条岗位，592 条有描述，全部招聘状态为 unknown（未核验）。独立 RAG 全描述匹配 424 条，扩展 RAG/GraphRAG/RAGFlow 为 426 条。章节规则将职责/任职要求主样本确定为 **{n} 条**。主样本外有 12 条未知章节待判定，以及 31 条在加分章节出现 RAG；两组有 2 条交集。主样本中另有 167 条含未知章节文本，可能遗漏技术提及。

主样本按职责/任职要求的固定技术词表统计，每岗每类只计一次；不同类可共现。以下是规则事实，未经逐岗语义确认，不等同于必备要求，也不证明直接用于 RAG。

| 技术组 | 岗位数 | 占 {n} 条比例 |
|---|---:|---:|''')
    for c in categories:text.append(f"| {c['label']} | {c['job_count']} | {c['fraction']:.1%} |")
    text.append('''
技术提及呈现出 Agent/业务应用集成、检索链路和后端部署三个方向，但这里的方向划分属于分析解释。文档处理、检索优化、评测等合并组的匹配可能较宽：例如模型的“召回率”也会命中检索优化，仍需人工判断与 RAG 的关系。完整条件分组、词表和局限见 `metrics.json` 及前一份规则报告。

## 3. 内置模型生成：原始输出与来源

以下逐段保留三轮生产内置生成输出，不以人工润色掩盖模型错误。各轮的 [1] 等引用只对应紧随其后的该轮来源表，编号不会跨轮复用为同一岗位。每轮最多八份来源，允许来源重叠，不能从这些段落得出全库频次或完整能力覆盖。
''')
    for name,label in [('overview','技术要求总览'),('retrieval','检索链路细节'),('engineering','应用与工程能力')]:
        r=results[name]
        text.append(f'### {label}\n\n'+r['answer']+'\n\n该轮引用来源（版本及证据另见 `generated_answers.json`）：\n\n| 编号 | 岗位 | ID | 状态 |\n|---|---|---|---|')
        for i,j in enumerate(r['results'],1):
            text.append(f"| [{i}] | [{j['title'].replace('|','/')} · {j['company'].replace('|','/')}]({j['url']}) | `{j['key']}` | {j['job_status']} |")
    text.append(f'''
## 4. 首轮模型输出中已观察到的问题

技术总览的原始回答把 2026-10-23 写成“未来时间”；本次实际运行日期是 2026-11-01，因此该判断错误。它还在开头声称八份来源都在职责/要求出现 RAG，却在后文排除了第 [4] 份“高级Java（RAG）”，口径前后不一致。第 [4] 份只在标题出现 RAG，不在全描述 426 条样本中，说明语义召回和模型重排本身不能替代描述字段的精确筛选。

总览还把第 [4] 份的“所有技术要求”写成优先项，但提供给生成模型的 qualification_context 中，“精通Java语言，熟悉Spring、Spring Boot、Spring Cloud等主流框架”没有优先修饰；容器/大数据等部分条目才有“者优先”。因此条件标签和完整上下文均已存在时，生成仍可能错误地将某一条的优先性质扩散至其他条目。总览中“必备工具链”表也包含它自己注明为加分的第 [5] 份来源，分类表仍有混杂。

检索链路回答也错误地称采集日期为未来时间；还在 Embedding 条目中使用“向量检索隐含Embedding使用”，以及将 bad case 分析解释为涉及重排。这些是模型推断，不能作为原文明确要求相应技术的证据，应由人工逐项区分。

以上是有原始输出和来源可查的缺陷观察，不是全量准确率测量。它们说明本轮完成了模型链路执行，同时发现了口径筛选、时间判断和条件关系理解问题。模型在末尾自称“未将优先升格为必备”等，不构成正确性证据；人工应按原文独立判断。

## 5. 与首轮参考回答如何交给人工比较

参考报告仍为 `rag-job-requirements-baseline-v1.md`。总岗位 593、全描述独立 RAG 424、扩展样本 426 与其数字一致。全描述下 Python 280、Embedding 64、MCP 115 也一致。但首轮没有逐 JD 标签、文件哈希和完整词表，数字一致不能证明逐岗集合或语义判断一致。

本轮职责/任职要求规则主样本是 {n} 条，首轮 V1 主口径是全描述 426 条。其附注的“另一报告 392 条”不能直接作为召回标准。词表分类也存在合并差异，因此不把两张技术表直接计算准确率。

人工分三层检查：

1. `review_jobs.csv`：426 份完整 JD，判断 RAG 是否确在职责/要求主体，以及规则漏提取的技术；优先审阅 unknown 和加分项分组。
2. `review_evidence.csv`：5,019 条主样本返回证据，确认技术提及、必备/优先/否定/任选及其直接 RAG 关系。字符位置已校验，不表示语义已校验。
3. `review_generation.csv`：三轮原始生成回答，核对每条引用是否支持结论、是否将优先/任选写成必备、是否把样本结论推广到全库，并与首轮答案对比。

所有人工列留空，`semantic_count_complete=false`。模型真正被调用不等于已得到人工标准答案，也不意味着整体答案自动优于首轮分析。

## 6. 本轮发现及改动

前次执行主动关闭了模型，未满足完整模型流程要求。检查后确认现有 Embedding 和 Rerank 配置有效；同一百炼凭据也成功通过 `qwen-plus` 生成探针。本次实际使用这三个模型。

代码还存在一个流程连接缺口：候选接口支持重排，但 `answer()` 内置生成原先直接使用混合检索顺序。本次为 `SearchRequest` 增加默认关闭的 `rerank` 开关，并让 `answer()` 在生成前调用原有完整 JD 重排能力；仅在显式启用时执行，失败会保留明确原因。正式运行开启该开关，并断言三轮全部 `applied=true`；单元测试验证生成接收到的是重排后来源顺序。

三轮调用通过的是生产函数，不是替身响应或虚构向量；网络为真实 HTTPS。正式模型运行没有额外经过 MCP，前一轮 44 次真实 MCP 调用负责全库统计、全文读取与接口路径验证。二者在报告中分别记账，不把前一次 MCP 次数计作真实模型次数。

## 7. 能力、产物与验证

| 能力 | 产物与判定 |
|---|---|
| 导入及规范化 | `{args.run}/import.json`；隔离 `models.db` |
| 分块及真实向量索引 | `index.json`、`stats.json`；{stats['indexed']} 岗位索引就绪，{stats['vectors']} / {stats['chunks']} Chunk 具备向量 |
| 混合召回、重排、内置生成 | `overview.json`、`retrieval.json`、`engineering.json`；三轮均为 hybrid / applied / llm |
| 调用审计 | `provider_calls.jsonl`；正式运行 {len(calls)} 次成功响应 |
| 全库目录/技术计数/证据定位 | 前轮 44 次真实 MCP、5,019 条主样本返回证据原文位置校验；本轮复用相同文件输入的统计 |
| 模型原始输出与审阅 | `generated_answers.json`、`review_generation.csv`，含各轮完整来源和证据 |
| 人工对照 | `review_jobs.csv`、`review_evidence.csv`、`review_generation.csv`，尚无人工标签 |
| 数据及实现追溯 | `model-manifest.json`、`rule-manifest.json`、`artifacts.json` |

相关自动化验证：101 项通过，覆盖导入、分块、目录、技术统计、候选检索、重排、生成和两者的连接。该结果是本次实际执行记录，并非报告脚本会自动运行的测试。模型生成只做了基本引用编号有效性校验和来源状态复核；事实支持程度、引用是否充分以及推理质量仍需人工审查。

独立模型探针原始输出位于 `runtime/experiments/rag-tech-real-models/probe.json`。探针生成曾把 2026-10-23 错称为未来日期，并把 unknown 延伸为疑似失效，表明真实模型也会产生错误；该段为探针输出，不作为本报告的招聘事实。三轮正式原始输出均保留，便于审查同类问题。

完整模型运行文件在 `{args.run}`，受 Git 忽略，需另行归档。当前报告目录保存可携带的调用记录、模型答案、统计与人工表，不包含数据库及向量原值。CSV SHA-256：`{manifest['csv_sha256']}`。规则轮与模型轮实现指纹不同，分别见各自 manifest；模型续跑之前的实现指纹保存在 `attempt-manifests.json`，不能将复用的第一轮回答说成由续跑代码重新生成。

## 8. 复现

从仓库根目录执行，需要现有 `.env.experiments` 中有效的百炼配置及真实模型访问权限；命令会产生实际模型调用：

```bash
.venv/bin/python experiments/rag_tech_requirements/scripts/run_models.py --output runtime/experiments/rag-tech-real-new
.venv/bin/python experiments/rag_tech_requirements/scripts/build_model_report.py --run runtime/experiments/rag-tech-real-new --rule-report experiments/rag_tech_requirements/results/2026-11-01/rules --output experiments/rag_tech_requirements/results/new/models
```

模型执行入口可在同一输出目录重试：完成的索引任务保留，成功回答存在时复用；汇总时以整个 provider 日志为准。不要在已运行目录更换源 CSV、实现或模型配置后声称同一次实验；新实验应使用新目录。报告打包脚本要求报告输出目录尚不存在。上述复现命令复用本次冻结的规则统计；若更换 CSV，必须先重跑 `run_pipeline.py` 及 `build_report.py`，否则打包脚本会因文件哈希不一致而拒绝。
''')
    (args.output/'report.md').write_text('\n'.join(text))
    write('artifacts.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.iterdir()) if p.is_file()})
    print(json.dumps({'report':str(args.output/'report.md'),'model_responses':len(calls),'vectors':stats['vectors']},ensure_ascii=False))


if __name__=='__main__': main()
