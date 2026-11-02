# apply-flow · 公司与岗位工作内容分析 + 沟通投递

这个目录是**使用 Job-RAG 数据的应用工作流**，不属于 `job_rag/` 核心知识库。它只做两件事：

1. **分析**：用 skill `job-apply-analysis` 读岗位描述、公司介绍和简历技术背景，回答“公司在做什么、岗位具体做什么”，写入 `data/jobs.csv` 的 `analysis` 字段。
2. **沟通投递**：人工确认后，运行同目录的 `apply_job.mjs`，只对指定 `job_id` 点击一次“立即沟通”，并记录聊天页内容。

这是“理解岗位”的分析，不是人岗匹配评分。分析不会发消息；点击必须显式加 `--confirm`。

## 目录

| 文件 | 用途 |
|---|---|
| `.claude/skills/job-apply-analysis/SKILL.md` | 公司与岗位工作内容分析 skill（主流程） |
| `set_analysis.py` | 把结论安全写回 `jobs.csv.analysis` |
| `resume_skills_projects.md` | 供岗位理解使用的技能与项目背景摘要，不是采集源数据 |
| `apply_job.mjs` | 招聘业务编排：校验 `analysis`、读取岗位、调用 browser-ops 沟通动作，结果只打印到终端 |

浏览器动作不在本目录：`browser-ops/extensions/boss/contact.mjs` 负责打开岗位页、识别按钮、点击一次和读取聊天页；它不读取 `jobs.csv`、不做岗位分析。两者关系：

```text
apply-flow/apply_job.mjs          # 招聘业务：选岗位、查 analysis、人工确认、记录结果
        ↓ 调用
browser-ops/extensions/boss/contact.mjs   # 浏览器动作：找按钮、点击、读聊天页
```

## 输入

| 文件 | 用途 |
|---|---|
| `data/jobs.csv` | 岗位描述、公司、标题、关键词 |
| `data/company/company_info.csv` | 公司介绍和业务信息；同一职位重复记录需去重。该文件从旧 `collections/` 目录原样移入 |
| `apply-flow/resume_skills_projects.md` | 简历技能与项目背景，仅作技术语境参考 |

## 使用

### 1. 分析

在 Claude Code 中调用 skill `job-apply-analysis`，指定 `job_id`。Skill 会：

- 读取岗位描述和公司介绍；
- 回答“公司在做什么、岗位具体做什么”；
- 通过 `set_analysis.py` 写入 `jobs.csv.analysis`。

结论使用两段式，建议 200–350 字：

```text
公司在做什么：<主营业务、产品/内容平台、服务对象、AI 在业务中的作用>。
岗位具体做什么：<业务问题、技术重心、日常工作、交付成果；未确认的写推测/待确认>。
```

示例（太平洋网络）：

```text
公司在做什么：太平洋网络是一家以垂直内容平台为主要业务的互联网公司，旗下包括太平洋科技、太平洋汽车、太平洋家居、太平洋时尚和太平洋亲子等平台；主营业务不是 AI 模型或 AI 原生产品，AI 更可能是支撑内容生产和运营的技术能力。岗位具体做什么：JD 侧重图像、视频及多模态生成与理解，包括文生图、图生图、文生视频、模型训练与微调、评测及推理部署；结合公司业务推测，岗位主要为内容平台提供 AIGC 技术能力，技术重心偏多模态算法，RAG/Agent 并非核心职责；具体服务哪条业务线尚未确认。
```

不要写进结论：

- 工商信息、注册资本、融资历史、公司规模；
- 技能匹配评分、硬门槛汇总、投递建议、面试准备。

### 2. 人工确认

阅读 `jobs.csv` 的 `analysis` 字段，决定是否投递。

### 3. 沟通投递

确认后运行：

```bash
node apply-flow/apply_job.mjs --job-id <job_id> --confirm
```

脚本行为：

- `apply_job.mjs` 读取 `jobs.csv`、校验 `analysis`、要求 `--confirm`；
- 调用 `browser-ops/extensions/boss/contact.mjs`；
- contact 动作：
  - 打开岗位页并切到前台；
  - 检查按钮：
    - “立即沟通”：点击一次；
    - “继续沟通”：说明已联系过，不再点击；
    - 已关闭/被遮挡/验证页：停止并报告；
  - 点击成功后打开消息页，记录新会话和默认招呼语；
- apply-flow 只把结果打印到终端，不生成 JSON/TXT 报告文件；
- 若按钮从“立即沟通”变为“继续沟通”（本次发送成功），或按钮本来就是“继续沟通”（已有沟通记录），脚本会把 `jobs.csv` 中该岗位的 `status` 自动改为 `已投递`；
- 投递失败、按钮消失、验证页或其他错误不改状态，结果只输出到本次命令的 stdout；
- 状态写入失败不会回滚已发送消息，报告里会给出 `status_error`，需按提示人工处理。

如果 browser-ops 不在相邻目录，可用环境变量指定 contact 脚本：

```bash
BROWSER_OPS_CONTACT=/path/to/browser-ops/extensions/boss/contact.mjs \
  node apply-flow/apply_job.mjs --job-id <job_id> --confirm
```

## 注意

- `analysis` 必须非空；为空时脚本拒绝点击，需加 `--allow-empty-analysis` 才能绕过。
- `company_info.csv` 可能因为同一职位多批次采集包含重复公司信息；分析时需按职位 ID 去重。
- 数据合并只维护采集字段，保留 `jobs.csv` 的人工 `analysis` 与既有 `status`，不会自动触发投递动作。
- `resume_skills_projects.md` 存放在公开仓库中，请避免放入私人联系方式、凭据或其他不宜公开的履历信息。
- 匿名/猎头岗位可能没有公司介绍，分析应标注“公司业务信息缺失/待确认”。
- 默认招呼语是账号统一模板，不随岗位变化；批量点击前需考虑风控和消息质量。
