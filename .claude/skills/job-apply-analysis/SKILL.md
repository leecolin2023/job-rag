---
name: job-apply-analysis
description: Analyze a BOSS job as "what the company does + what the job actually does" using data/jobs.csv, data/collections/公司信息.csv and data/resume_skills_projects.md; write a two-part understanding conclusion into jobs.csv analysis. Use when the user asks to analyze a job, understand the work behind a job, or fill jobs.csv analysis for a job_id.
---

# 公司与岗位工作内容分析（写入 jobs.csv.analysis）

投递前只回答两个问题：

1. **这家公司在做什么生意？** 它向谁提供什么产品或服务？AI 在业务中扮演什么角色？
2. **我进去之后具体做什么？** 解决什么业务问题、使用什么技术、日常做什么、最终交付什么？

这是“理解岗位”的分析，不是“人岗匹配评分”。

## 输入

- 必填：`job_id`
- 读取：`data/jobs.csv` 中该行的 `title/company/location/description/url/keywords`
- 读取：`data/collections/公司信息.csv` 中 `职位ID == job_id` 的公司介绍和业务信息；同一职位可能重复，先去重/合并
- 读取：`data/resume_skills_projects.md` 作为技术语境参考，帮助你理解岗位术语和可能的工作方式

## 分析重点

### 1. 公司在做什么

- 主营业务、核心产品/内容平台、服务对象；
- AI 在这家公司业务中的位置：是主营产品、降本增效工具，还是尚未成为核心；
- 只使用公司介绍和业务描述，不要用工商信息、注册资本、融资历史、公司规模来替代业务分析。

### 2. 岗位具体做什么

- 解决什么业务问题：这个岗位为哪条业务线、哪类内容或流程服务；
- 技术重心：从 JD 的职责、硬性要求、加分项判断，哪部分是核心，哪部分只是附带；
- 日常工作：模型训练/微调、评测、推理部署、应用开发、数据工程等，按 JD 说明；
- 交付成果：最终产出是什么（模型能力、内容生成能力、推理服务、业务系统等）；
- 无法从 JD/公司介绍确认的内容，明确写“推测”或“待确认”，不要编造。

## 输出

在聊天里只给 3–5 条短要点，不写长报告。

写入 `jobs.csv.analysis` 的结论使用两段式，建议 200–350 字，最多 500 字：

```text
公司在做什么：<主营业务、产品/内容平台、服务对象、AI 在业务中的作用>。
岗位具体做什么：<业务问题、技术重心、日常工作、交付成果；未确认的写推测/待确认>。
```

示例（太平洋网络）：

```text
公司在做什么：太平洋网络是一家以垂直内容平台为主要业务的互联网公司，旗下包括太平洋科技、太平洋汽车、太平洋家居、太平洋时尚和太平洋亲子等平台；主营业务不是 AI 模型或 AI 原生产品，AI 更可能是支撑内容生产和运营的技术能力。岗位具体做什么：JD 侧重图像、视频及多模态生成与理解，包括文生图、图生图、文生视频、模型训练与微调、评测及推理部署；结合公司业务推测，岗位主要为内容平台提供 AIGC 技术能力，技术重心偏多模态算法，RAG/Agent 并非核心职责；具体服务哪条业务线尚未确认。
```

### 不要写进结论

- 工商信息、注册资本、融资历史、公司规模等常规信息；
- 技能匹配评分、硬门槛汇总、投递建议、面试准备；
- 只有技术标签、看不出公司业务和具体产出的短句。

## 写回 jobs.csv

不要手工编辑 CSV（description 含换行/引号）。使用：

```bash
python3 apply-flow/set_analysis.py --job-id <job_id> --analysis '<结论>'
```

写入后读回该行确认 `analysis` 已更新，并把结论原样告诉用户。

## 确认后沟通投递

分析只负责写入结论，**不点击、不发送**。

等用户明确确认可以投递后，才运行：

```bash
node apply-flow/apply_job.mjs --job-id <job_id> --confirm
```

要求：

- 一次只处理一个 `job_id`
- 必须显式 `--confirm`
- 不批量、不循环、不跳过人工确认
- 脚本会检查 `analysis` 非空；按钮为“继续沟通”时不会重复点击
- 点击后记录聊天页内容和发送结果
