# 2026-10-30 广州、深圳岗位合并与状态更新报告

> **状态规则更正（2026-10-31）：** 本报告的 204 条 `下线` 及相关“按搜索批次差集判定下线”的结论已撤销。`data/jobs.csv` 中全部 1,324 条岗位的 `status` 已统一恢复为 `招聘中`；新批次未检索到旧岗位，不能推断其下线。以下数据及 204 条清单仅保留为**当时合并过程的历史记录**，不代表当前有效状态或已证实岗位关闭。


## 范围

新采集文件（原样保留）：

- [广州 Agent](guangzhou-agent.csv)：299 条
- [广州 RAG](guangzhou-rag.csv)：300 条
- [深圳 Agent](shenzhen-agent.csv)：300 条

旧版参照：`data/jobs.csv` 原有 593 个职位 ID；2026-10-23 的 [广州 Agent](../2026-10-23/guangzhou-agent.csv)、[广州 RAG](../2026-10-23/guangzhou-rag.csv) 搜索结果，共计 545 个不同的旧职位 ID。

## 合并结果

| 指标 | 数量 |
|---|---:|
| 本轮采集原始记录 | 899 |
| 本轮按职位 ID 去重 | 841 |
| 本轮广州 Agent 与广州 RAG 交集 | 58 |
| 旧版主表 | 593 |
| 本轮再次采集到的旧职位 | 341 |
| 新增职位 | 500 |
| 10 月 23 日 Agent/RAG 旧职位，本轮未再采到 | 204 |
| 旧版其他关键词职位，本轮未再采到 | 48 |
| **合并后唯一职位** | **1,093** |
| **status=招聘中** | **889** |
| **status=下线** | **204** |

## 状态判定规则

按本次使用者指定的**搜索批次差集**口径：

1. 原主表内且属于 10 月 23 日广州 Agent/RAG 采集范围的岗位，如果在 10 月 30 日的广州 Agent、广州 RAG、深圳 Agent 三份文件的职位 ID 并集中均不存在：标为 **`下线`**。
2. 本轮采集到的旧岗位与新增岗位：标为 **`招聘中`**。
3. 原主表中的其余 48 条非上述旧 Agent/RAG 来源岗位，本轮并没有对应 vLLM、SGLang、LangChain 等关键词复查；依使用者指定的“其他都招聘中”规则保留并标为 **`招聘中`**，但不能理解为本轮已核实在线。

**重要：`下线` 在此只是本次关键词采集未命中的工作状态，不是 BOSS 官方已关闭的网页证据。** 由于页面排序、搜索召回、前 300 条结果截断等原因，这 204 条不宜在没有独立访问核验前用于正式的招聘存量/职位关闭率统计。与其说职位实际下线，更准确的事实是“本轮未再采集到”。

**字段兼容性警告：** 此前 `jobs.csv.status` 表示“详情采集成功/失败”，本轮依据要求改为“招聘中/下线”两个值。项目当前 `job_rag.storage.Job.job_status` 是另一套独立状态，普通 `job-rag import` 不会自动把 CSV 的 `status` 写入 `job_status`，不能据此声称线上数据库状态同步成功。

## 字段合并规则

- 按来源平台职位 ID 合并，保留全部原始 593 条，并加入 500 个新 ID，不删除历史岗位。
- 同时出现在 10/30 广州 Agent/RAG 的 58 个岗位，优先采用较晚的 10/30 网页采集记录。两份记录的 11 个其他字段一致，仅部分“技能标签”不同。
- 对再次采集到的旧岗位，以本次有值的最新标题、公司、薪酬、经验、学历、网址、JD 替换旧值。仅当最新字段非空且不是占位符时覆盖，避免损伤完整历史正文。
- **旧版具体地址定位更精细：** 新文件的 `工作区域` 仅为“广州”或“深圳”，对城市一致的历史岗位保留更细的区级 `location`，以免丢失地址筛选精度。
- `collected_at` 在本主表中采用“最后一次被采集日期”口径：再次采集或新增的岗位记为 `2026-10-30`；旧版未再次采到的保留 `2026-10-23`。原始快照精确到秒的时间戳保留在三个采集文件中。
- `keywords` 保存历史与本次已出现的搜索关键词并集；本轮的 `技能标签` 未加入 12 列的标准主表。
- 三份采集 CSV 和旧版 10/23 快照保持不变；`data/jobs.csv` 仍为 12 列 UTF-8 with BOM 数据格式。

## 状态差集清单

以下 204 条属于 **2026-10-23 Agent/RAG 旧样本中本轮未再次出现** 的岗位，按指令标记“下线”（未网页核验关闭）。

| 职位 ID | 原岗位名称 | 原搜索关键词 | 链接 |
|---|---|---|---|
| `5a8aa14f8f3c8bb50ndz29y_FlZU` | IT项目经理（AI方向） | vLLM；sglang；RAG | [详情页](https://www.zhipin.com/job_detail/5a8aa14f8f3c8bb50ndz29y_FlZU.html) |
| `9a5950e9d4fd202a0nx70t67GFpV` | 高级ai工程师 | vLLM；sglang；RAG | [详情页](https://www.zhipin.com/job_detail/9a5950e9d4fd202a0nx70t67GFpV.html) |
| `0f9ea6023f32ec040nN40tm4ElBW` | FDE专家 | vLLM；RAG | [详情页](https://www.zhipin.com/job_detail/0f9ea6023f32ec040nN40tm4ElBW.html) |
| `178a46d7316f1a360nNy3d60FlNR` | AI大模型讲师 | vLLM；RAG | [详情页](https://www.zhipin.com/job_detail/178a46d7316f1a360nNy3d60FlNR.html) |
| `c48082eb499fff0f0nN_3NS0F1JZ` | Java/Go 后端工程师（大模型平台·GPU方向） | vLLM；RAG | [详情页](https://www.zhipin.com/job_detail/c48082eb499fff0f0nN_3NS0F1JZ.html) |
| `17e98ec61b20bfd50nx62Nu4EVNU` | agent框架工程师 | vLLM；Agent | [详情页](https://www.zhipin.com/job_detail/17e98ec61b20bfd50nx62Nu4EVNU.html) |
| `2d3bea67271372080nJ50tm9E1pQ` | Agent开发工程师 | vLLM；Agent；RAG | [详情页](https://www.zhipin.com/job_detail/2d3bea67271372080nJ50tm9E1pQ.html) |
| `37bf3f6943fb53fa0nN909i6E1BS` | AI工程师（Agentic AI / 智能体）AI Agent | Agent | [详情页](https://www.zhipin.com/job_detail/37bf3f6943fb53fa0nN909i6E1BS.html) |
| `b016ce95886f12500nN80tS7FFpU` | Agent训练师 | Agent | [详情页](https://www.zhipin.com/job_detail/b016ce95886f12500nN80tS7FFpU.html) |
| `702e9b55496ff9ea0nx60t6_FFRU` | AI Agent 高级产品负责人 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/702e9b55496ff9ea0nx60t6_FFRU.html) |
| `7b001398c567b4560nx73Nq8EVFT` | AI Agent开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/7b001398c567b4560nx73Nq8EVFT.html) |
| `8571307a88c9b8120nB63Nq1GVFU` | AI Agent 产品研发工程师（应届生） | Agent | [详情页](https://www.zhipin.com/job_detail/8571307a88c9b8120nB63Nq1GVFU.html) |
| `bee2e5c360d8361e0nB_0tq9GVpU` | AI Agent大客户销售 带教体系完善 25届可投 | Agent | [详情页](https://www.zhipin.com/job_detail/bee2e5c360d8361e0nB_0tq9GVpU.html) |
| `256de0e152e67aec0nN509i-ElRV` | 招人｜企业 AI 知识库架构与 RAG 检索优化 | RAG | [详情页](https://www.zhipin.com/job_detail/256de0e152e67aec0nN509i-ElRV.html) |
| `7257c0cf78f48cf20nJ93ty-FVZQ` | 产品经理（Ai方向） | RAG | [详情页](https://www.zhipin.com/job_detail/7257c0cf78f48cf20nJ93ty-FVZQ.html) |
| `eec4199fd295cc480nx739S-FFVS` | AI Agent产品经理 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/eec4199fd295cc480nx739S-FFVS.html) |
| `dcd561fa7ff973e20nN509i-EFtW` | 招｜企业 Agent 应用工程师（落地派） | Agent | [详情页](https://www.zhipin.com/job_detail/dcd561fa7ff973e20nN509i-EFtW.html) |
| `924c442d4737dbce0nNy2d68GFpW` | Agent 开发工程师（AI 智能体方向） | Agent | [详情页](https://www.zhipin.com/job_detail/924c442d4737dbce0nNy2d68GFpW.html) |
| `ca5c53bf2640c0c50nJ709m6FFJU` | AI Agent Engineer（外企，英语口语沟通） | Agent | [详情页](https://www.zhipin.com/job_detail/ca5c53bf2640c0c50nJ709m6FFJU.html) |
| `4ffc8ff4d0a097bb0nx63ti6GFZR` | AI Agent 产品经理 | Agent | [详情页](https://www.zhipin.com/job_detail/4ffc8ff4d0a097bb0nx63ti6GFZR.html) |
| `43e28e0bc4e2f7bb0nN_2Nu1GFtX` | 数据产品经理（AI agent+Python） | Agent | [详情页](https://www.zhipin.com/job_detail/43e28e0bc4e2f7bb0nN_2Nu1GFtX.html) |
| `2c3d80d403aa42fa0nx53dW1F1dS` | B端ai产品经理（PE、agent提效）-双休 | Agent | [详情页](https://www.zhipin.com/job_detail/2c3d80d403aa42fa0nx53dW1F1dS.html) |
| `7c9b226c0cf5189e0nx539q-FlFZ` | AI Agent开发工程师 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/7c9b226c0cf5189e0nx539q-FlFZ.html) |
| `d81c4e0645d0026e0nN-2N-4EFJT` | Agent架构 | Agent | [详情页](https://www.zhipin.com/job_detail/d81c4e0645d0026e0nN-2N-4EFJT.html) |
| `388cfdc153a80de20nx72dq4E1tU` | Agent全栈开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/388cfdc153a80de20nx72dq4E1tU.html) |
| `6dddf94fd756c1980nN929u_GFFZ` | 电商行业架构师（B2C） | Agent | [详情页](https://www.zhipin.com/job_detail/6dddf94fd756c1980nN929u_GFFZ.html) |
| `3f83a900d8a778000nx70964GFtT` | 金融国企-AI应用开发 | Agent | [详情页](https://www.zhipin.com/job_detail/3f83a900d8a778000nx70964GFtT.html) |
| `263511704b18ca490nx53dq5EVVY` | Agent语音/大模型语音 | Agent | [详情页](https://www.zhipin.com/job_detail/263511704b18ca490nx53dq5EVVY.html) |
| `e2d8eec16923ffdc0nNz2ty0E1JR` | 电商 AI Agent 工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/e2d8eec16923ffdc0nNz2ty0E1JR.html) |
| `f1140d74980359020nN929m8EFFT` | 前端工程师-AI Agent智能体-211+ | Agent | [详情页](https://www.zhipin.com/job_detail/f1140d74980359020nN929m8EFFT.html) |
| `3aa00961cc4608120nx429S-GFdR` | Agent开发（广州） | Agent | [详情页](https://www.zhipin.com/job_detail/3aa00961cc4608120nx429S-GFdR.html) |
| `0527a6b459c2c86d0nJ93tm4F1ZQ` | AI Agent产品经理（上市公司/AI前沿） | Agent | [详情页](https://www.zhipin.com/job_detail/0527a6b459c2c86d0nJ93tm4F1ZQ.html) |
| `dba4170d7bb7c4820nx42du6FVJU` | agent开发（短剧方向） | Agent | [详情页](https://www.zhipin.com/job_detail/dba4170d7bb7c4820nx42du6FVJU.html) |
| `884685c120a1cf870nJ53NW5FFRY` | Agent实习生 | Agent | [详情页](https://www.zhipin.com/job_detail/884685c120a1cf870nJ53NW5FFRY.html) |
| `4fe17528d409492e0nN92Nm7EFdV` | AI产品经理 | Agent | [详情页](https://www.zhipin.com/job_detail/4fe17528d409492e0nN92Nm7EFdV.html) |
| `398a0453f1b29f7a0nx42t--F1JQ` | Python开发AI Agent 方向 | Agent | [详情页](https://www.zhipin.com/job_detail/398a0453f1b29f7a0nx42t--F1JQ.html) |
| `2041f510a5b057c20nF_3N68GVBR` | AI agent产品经理 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/2041f510a5b057c20nF_3N68GVBR.html) |
| `08030772d7dcc25f0nx50ti0FFVW` | ai agent【财务方向】 | Agent | [详情页](https://www.zhipin.com/job_detail/08030772d7dcc25f0nx50ti0FFVW.html) |
| `d439273c60fb27f70nx62dW7FFRV` | AI原生ToB销售（OPC超级个体） | Agent | [详情页](https://www.zhipin.com/job_detail/d439273c60fb27f70nx62dW7FFRV.html) |
| `0198a5c8cb08f8ba0nx42d-1GVRU` | FDE工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/0198a5c8cb08f8ba0nx42d-1GVRU.html) |
| `af7999fc807d2d420nx529S4FVNY` | agent开发 | Agent | [详情页](https://www.zhipin.com/job_detail/af7999fc807d2d420nx529S4FVNY.html) |
| `2e15f2213658bbe60nN929u4EFpY` | AI Agent工程师（熟悉ReAct具备DataAgent） | Agent | [详情页](https://www.zhipin.com/job_detail/2e15f2213658bbe60nN929u4EFpY.html) |
| `e62af7b635b1ba060nZ53d-1E1RR` | Agent工程师 (MJ000163) | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/e62af7b635b1ba060nZ53d-1E1RR.html) |
| `daf6ca5c188c1d7e0nx70tW_FFJV` | Agent开发工程师（大模型方向） | Agent | [详情页](https://www.zhipin.com/job_detail/daf6ca5c188c1d7e0nx70tW_FFJV.html) |
| `8ce79f84eb14fb880nx509q8E1RS` | AI Agent 全栈工程师（FDE） | Agent | [详情页](https://www.zhipin.com/job_detail/8ce79f84eb14fb880nx509q8E1RS.html) |
| `7d0bd7e32ed1477c0nJz3Ni1FFRS` | Agent开发工程师-高级 | Agent | [详情页](https://www.zhipin.com/job_detail/7d0bd7e32ed1477c0nJz3Ni1FFRS.html) |
| `0b9a7bfb8f640d670nJz3ti8GVBX` | AI开发工程师（Agent平台架构方向） | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/0b9a7bfb8f640d670nJz3ti8GVBX.html) |
| `7e0a3d52907c9e620ndy2NW8GFZQ` | AI Agent 全栈工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/7e0a3d52907c9e620ndy2NW8GFZQ.html) |
| `027dc0fa98dce4a50nF73d68FlBU` | 产品经理/Agent构建平台 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/027dc0fa98dce4a50nF73d68FlBU.html) |
| `3c388d3708d0a68c0nNy2Ny-F1JZ` | AI Agent工程开发工程师（实习岗） | Agent | [详情页](https://www.zhipin.com/job_detail/3c388d3708d0a68c0nNy2Ny-F1JZ.html) |
| `8bdd2f3a150079030nN93dW8EVNW` | AI Agent 产品运营（社交拟人方向） | Agent | [详情页](https://www.zhipin.com/job_detail/8bdd2f3a150079030nN93dW8EVNW.html) |
| `6eda4c72cdea895d0nJ_3di9EVNV` | 软件测试工程师（data/AI） | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/6eda4c72cdea895d0nJ_3di9EVNV.html) |
| `c05d5ddb319892d70nx72tu5F1RU` | 前台接待 Front Desk Service Agent | Agent | [详情页](https://www.zhipin.com/job_detail/c05d5ddb319892d70nx72tu5F1RU.html) |
| `18452beb5001b2e70nx43NW_F1ZV` | 中级Agent研发工程师（广州-天河区） | Agent | [详情页](https://www.zhipin.com/job_detail/18452beb5001b2e70nx43NW_F1ZV.html) |
| `e3bdb3e7f7be88d10nN7396_E1JT` | Agent 开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/e3bdb3e7f7be88d10nN7396_E1JT.html) |
| `1f80b879aecd46360nN60tu0FFNU` | B端 AI产品经理/运营 | Agent | [详情页](https://www.zhipin.com/job_detail/1f80b879aecd46360nN60tu0FFNU.html) |
| `a876bb8df83ec3ce0nN-0tu6FFpT` | AI 应用工程师（Agent／工作流方向） | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/a876bb8df83ec3ce0nN-0tu6FFpT.html) |
| `16398560e08aed5b0nN629W8GVVU` | Agent 系统架构师 | Agent | [详情页](https://www.zhipin.com/job_detail/16398560e08aed5b0nN629W8GVVU.html) |
| `b220b7b19dc3153a0HJ82965FVM~` | 基金份额登记专员（Transfer Agent） | Agent | [详情页](https://www.zhipin.com/job_detail/b220b7b19dc3153a0HJ82965FVM~.html) |
| `144255f4a88d0a3b0nJ82dq9FVBQ` | AI 应用工程师（研发效能 / Agent 方向） | Agent | [详情页](https://www.zhipin.com/job_detail/144255f4a88d0a3b0nJ82dq9FVBQ.html) |
| `19848dd1ba2186220nN-0tW0EVpS` | java开发工程师（AI Agent） | Agent | [详情页](https://www.zhipin.com/job_detail/19848dd1ba2186220nN-0tW0EVpS.html) |
| `64be31538861d5550nV_0ty5FlJR` | Agent应用工程师 (Agent Engineer) | Agent | [详情页](https://www.zhipin.com/job_detail/64be31538861d5550nV_0ty5FlJR.html) |
| `09f739bb931a91100nx73dW7FlVR` | ai产品经理 | Agent | [详情页](https://www.zhipin.com/job_detail/09f739bb931a91100nx73dW7FlVR.html) |
| `460933fa0d71b87a0nJ53N--GVFR` | 全栈开发（偏后端） | Agent | [详情页](https://www.zhipin.com/job_detail/460933fa0d71b87a0nJ53N--GVFR.html) |
| `e91bef56caa3a2d90nx509S7FlJU` | AI Agent工程师（企业级安全、多智能体） | Agent | [详情页](https://www.zhipin.com/job_detail/e91bef56caa3a2d90nx509S7FlJU.html) |
| `7a0abe5dbaebd6660nx729y5GFRU` | AI Agent开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/7a0abe5dbaebd6660nx729y5GFRU.html) |
| `351afe6bb55c080e0nx52d-4E1VU` | AI 平台研发工程师 Al Agent Infra) | Agent | [详情页](https://www.zhipin.com/job_detail/351afe6bb55c080e0nx52d-4E1VU.html) |
| `e51e766d46099de60nx43t24FVRW` | Agent大模型专家（背靠三一稳定，不卷） | Agent | [详情页](https://www.zhipin.com/job_detail/e51e766d46099de60nx43t24FVRW.html) |
| `9068b943b1f3a46f0nN4396-F1NV` | Agent系统架构师 | Agent | [详情页](https://www.zhipin.com/job_detail/9068b943b1f3a46f0nN4396-F1NV.html) |
| `4b02a8db5b2725b50nN73ty5EFdR` | Agent研发工程师（双休+包2餐） | Agent | [详情页](https://www.zhipin.com/job_detail/4b02a8db5b2725b50nN73ty5EFdR.html) |
| `9f6d4512dec6803e0nN909q4ElVR` | 售前经理(智能语音客服) | Agent | [详情页](https://www.zhipin.com/job_detail/9f6d4512dec6803e0nN909q4ElVR.html) |
| `21162965af28442d0nZ709y-EVdU` | AI Agent 研发工程师 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/21162965af28442d0nZ709y-EVdU.html) |
| `979357c24dbbd5590nN93925GVtR` | Agent开发平台后端开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/979357c24dbbd5590nN93925GVtR.html) |
| `9378e8d7fe913fe70nN80t66F1FQ` | Agent Harness研发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/9378e8d7fe913fe70nN80t66F1FQ.html) |
| `7db8ce75b2f359290nx53tS0FFtY` | 电商Agent平台架构师 | Agent | [详情页](https://www.zhipin.com/job_detail/7db8ce75b2f359290nx53tS0FFtY.html) |
| `2b962f96d6689b780nx42t60EVtZ` | AI解决方案售前工程师（FDE方向） | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/2b962f96d6689b780nx42t60EVtZ.html) |
| `b28365264eb5f5180nx50tS0GVRW` | 运维开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/b28365264eb5f5180nx50tS0GVRW.html) |
| `766829d161d496490nN92dS8FVpS` | 全栈开发工程师（AI方向） | Agent | [详情页](https://www.zhipin.com/job_detail/766829d161d496490nN92dS8FVpS.html) |
| `cebf7e74c4a67f070nF83tW9FVBZ` | Senior AI Agent Expert / Architect | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/cebf7e74c4a67f070nF83tW9FVBZ.html) |
| `abd3bece81623f420nNy0tq7GVBT` | ai架构工程师 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/abd3bece81623f420nNy0tq7GVBT.html) |
| `56491e73c2af704b0nF72Nq9E1FS` | 知识产权AI应用FDE | Agent | [详情页](https://www.zhipin.com/job_detail/56491e73c2af704b0nF72Nq9E1FS.html) |
| `8d1a65c59222092a0nx53tm0FFBX` | 算法工程师（base深圳/线上面试/金融/双休 | Agent | [详情页](https://www.zhipin.com/job_detail/8d1a65c59222092a0nx53tm0FFBX.html) |
| `174b31dd407113850nx439i_F1RR` | ai技术经理 | Agent；RAG | [详情页](https://www.zhipin.com/job_detail/174b31dd407113850nx439i_F1RR.html) |
| `8a5d5bed007d05060nJ429S5F1ZZ` | AI产品解决方案专家（国企） | Agent | [详情页](https://www.zhipin.com/job_detail/8a5d5bed007d05060nJ429S5F1ZZ.html) |
| `b96695cdee83d60c0nFy09i8E1VU` | AI应用开发工程师 | Agent | [详情页](https://www.zhipin.com/job_detail/b96695cdee83d60c0nFy09i8E1VU.html) |
| `876703ab7a989bdd0nZ93t69FVdZ` | AI架构师(智能体&知识图谱方向) | Agent | [详情页](https://www.zhipin.com/job_detail/876703ab7a989bdd0nZ93t69FVdZ.html) |
| `c865568ed84e1cfc0nJ72dy_GFtU` | 产品经理（偏交付） | RAG | [详情页](https://www.zhipin.com/job_detail/c865568ed84e1cfc0nJ72dy_GFtU.html) |
| `493f1257adf34baf0nNz3NS9ElBU` | 全栈工程师（小程序+mvp后端） | RAG | [详情页](https://www.zhipin.com/job_detail/493f1257adf34baf0nNz3NS9ElBU.html) |
| `45156f79c9f9d33a0nN50tS9FlBS` | AI代码大模型工程专家【国企】 | RAG | [详情页](https://www.zhipin.com/job_detail/45156f79c9f9d33a0nN50tS9FlBS.html) |
| `77d4f2976eeee4530nN929S5E1BR` | 前端开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/77d4f2976eeee4530nN929S5E1BR.html) |
| `8d14e186abf7b5000nFz3tq8EVNQ` | AI开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/8d14e186abf7b5000nFz3tq8EVNQ.html) |
| `48072d7bafd8fbfb0nN72Nm5FlpX` | AI平台工程架构师（知识图谱与RAG方向） | RAG | [详情页](https://www.zhipin.com/job_detail/48072d7bafd8fbfb0nN72Nm5FlpX.html) |
| `60c0b77ca3da08f10nNy3d-7F1JZ` | AI 开发测试工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/60c0b77ca3da08f10nNy3d-7F1JZ.html) |
| `bb6edc1f50a11ffe0nN92Nu1FVZY` | AI解决方案工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/bb6edc1f50a11ffe0nN92Nu1FVZY.html) |
| `1b1924b441f483be0nN93t21GFZY` | 【2027校招】企业级 AI 技术管培生 | RAG | [详情页](https://www.zhipin.com/job_detail/1b1924b441f483be0nN93t21GFZY.html) |
| `965d038c5075ce280nB82Ni_EVNT` | 全栈AI工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/965d038c5075ce280nB82Ni_EVNT.html) |
| `c27b7e4c5d859faa0nJ-09q1FlJW` | [中台]游戏发行AI工程师（后端AI全栈） | RAG | [详情页](https://www.zhipin.com/job_detail/c27b7e4c5d859faa0nJ-09q1FlJW.html) |
| `254784eaedec60db0nN93d--FFVZ` | 中医产品经理（智能硬件及临床流程） | RAG | [详情页](https://www.zhipin.com/job_detail/254784eaedec60db0nN93d--FFVZ.html) |
| `67eccb05eedb2dce0nB92Nm4EVRS` | 全栈交付工程师（英语流利） | RAG | [详情页](https://www.zhipin.com/job_detail/67eccb05eedb2dce0nB92Nm4EVRS.html) |
| `5ea39247f73c6d110nFz29m8FVVW` | 电网方案解决专家 | RAG | [详情页](https://www.zhipin.com/job_detail/5ea39247f73c6d110nFz29m8FVVW.html) |
| `a2c9598f4e54d3920nx72di5FFtU` | Agent架构师 | RAG | [详情页](https://www.zhipin.com/job_detail/a2c9598f4e54d3920nx72di5FFtU.html) |
| `3b46f2039cd5b0b00nJ42tm8EVVZ` | AI应用工程师（持有工信部证书） | RAG | [详情页](https://www.zhipin.com/job_detail/3b46f2039cd5b0b00nJ42tm8EVVZ.html) |
| `9cee73e9309f51d30nN52NW_EFFT` | AI研发专家 | RAG | [详情页](https://www.zhipin.com/job_detail/9cee73e9309f51d30nN52NW_EFFT.html) |
| `945a64fbb01064930nx42du-FVJT` | AI 应用落地专员（Workbuddy） | RAG | [详情页](https://www.zhipin.com/job_detail/945a64fbb01064930nx42du-FVJT.html) |
| `309616a26e8c25cb0nZy3d21FlFR` | AI应用后台开发工程师-RAG-成都广州 | RAG | [详情页](https://www.zhipin.com/job_detail/309616a26e8c25cb0nZy3d21FlFR.html) |
| `20de435767de769a0nFy0t-1FVNS` | 知识库运营工程师（AI方向） | RAG | [详情页](https://www.zhipin.com/job_detail/20de435767de769a0nFy0t-1FVNS.html) |
| `c31cc9241e2878440nN92d-9EFpY` | AI产品经理(J10878) | RAG | [详情页](https://www.zhipin.com/job_detail/c31cc9241e2878440nN92d-9EFpY.html) |
| `35ffa883fbece59c0nJ_29i8E1RR` | 资深软件测试工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/35ffa883fbece59c0nJ_29i8E1RR.html) |
| `94333c3efc6187c90nx52d-9EVNY` | 游戏主程 | RAG | [详情页](https://www.zhipin.com/job_detail/94333c3efc6187c90nx52d-9EVNY.html) |
| `18b3c7ee3ee9bba60nB_09q7EldR` | AI应用产品经理（营销工具方向） | RAG | [详情页](https://www.zhipin.com/job_detail/18b3c7ee3ee9bba60nB_09q7EldR.html) |
| `3fd94a10fabc21640nx539W4E1dW` | AI/to大B交付工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/3fd94a10fabc21640nx539W4E1dW.html) |
| `9f860a7d25b61f830nB63Nq6E1VT` | AI Agent 产品研发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/9f860a7d25b61f830nB63Nq6E1VT.html) |
| `796425e0a79c07a10nZ53tu_EFpR` | 算法工程师（大模型应用算法规划与研发） | RAG | [详情页](https://www.zhipin.com/job_detail/796425e0a79c07a10nZ53tu_EFpR.html) |
| `16501e8a5db2a2a00nx72dS5GVNW` | AI应用产品经理（GEO产品化方向） | RAG | [详情页](https://www.zhipin.com/job_detail/16501e8a5db2a2a00nx72dS5GVNW.html) |
| `d037f1cab74fcfa70nN90921FlNS` | AI 产品经理（技术型 / 产品工程师） | RAG | [详情页](https://www.zhipin.com/job_detail/d037f1cab74fcfa70nN90921FlNS.html) |
| `f1795dac3b2443740nx63t6-GVBS` | AI全栈开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/f1795dac3b2443740nx63t6-GVBS.html) |
| `00f54e7a63dc90650nN92dy9FlNU` | ESL/班主任老师（近期到岗）和架构师 | RAG | [详情页](https://www.zhipin.com/job_detail/00f54e7a63dc90650nN92dy9FlNU.html) |
| `dfed84bb4ab905290nN53t-6EVNY` | 前端开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/dfed84bb4ab905290nN53t-6EVNY.html) |
| `62abb3d4287e2d120nJ73tu5E1JT` | 医疗产品（AI方向） | RAG | [详情页](https://www.zhipin.com/job_detail/62abb3d4287e2d120nJ73tu5E1JT.html) |
| `a22f5153c47252ae0nN93tW_FFBV` | AI智能体解决方案专家 | RAG | [详情页](https://www.zhipin.com/job_detail/a22f5153c47252ae0nN93tW_FFBV.html) |
| `1682051ab05969d30nFz2929GVRR` | 电力行业AI原生智能体架构师 | RAG | [详情页](https://www.zhipin.com/job_detail/1682051ab05969d30nFz2929GVRR.html) |
| `2aa1f04f7e0683a80nd42NW1FFBX` | AI Agent应用开发工程师（ | RAG | [详情页](https://www.zhipin.com/job_detail/2aa1f04f7e0683a80nd42NW1FFBX.html) |
| `cbd23a4ad6d0417f0nx50tm0F1FU` | FDE工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/cbd23a4ad6d0417f0nx50tm0F1FU.html) |
| `becdca379f7037230nN83di7FltU` | IT经理（AI技术方向） | RAG | [详情页](https://www.zhipin.com/job_detail/becdca379f7037230nN83di7FltU.html) |
| `66eca18d5d8851811XN73Ni4FFtR` | 全栈高级开发工程师(J13881) | RAG | [详情页](https://www.zhipin.com/job_detail/66eca18d5d8851811XN73Ni4FFtR.html) |
| `d576cab95dc6b1eb0nx70tW4FVRR` | Al解决方案销售专家（新签） | RAG | [详情页](https://www.zhipin.com/job_detail/d576cab95dc6b1eb0nx70tW4FVRR.html) |
| `ca9122b0af1156d80nN_3t-6F1RR` | Go 全栈开发工程师（AI Coding 方向） | RAG | [详情页](https://www.zhipin.com/job_detail/ca9122b0af1156d80nN_3t-6F1RR.html) |
| `43a3e6c41cdc34ce0nd43N-1FFFV` | ai技术经理 | RAG | [详情页](https://www.zhipin.com/job_detail/43a3e6c41cdc34ce0nd43N-1FFFV.html) |
| `766db54001e656800nx-29-7GVNT` | AI产品经理-法律智能业务(A98185) | RAG | [详情页](https://www.zhipin.com/job_detail/766db54001e656800nx-29-7GVNT.html) |
| `f5a0714abc54fb380nB-3N-_FVNR` | AI Agent 研发工程师（广告方向） | RAG | [详情页](https://www.zhipin.com/job_detail/f5a0714abc54fb380nB-3N-_FVNR.html) |
| `eb648e07523cd2ef0nN629S-EVNU` | 高级游戏测试工程师（AI TestAgent方向） | RAG | [详情页](https://www.zhipin.com/job_detail/eb648e07523cd2ef0nN629S-EVNU.html) |
| `60ac1f76b2a228190nJ-0t60EFFT` | Ai应用工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/60ac1f76b2a228190nJ-0t60EFFT.html) |
| `3eb8fc4d12d155810nJ90ti9FlZX` | ai后端开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/3eb8fc4d12d155810nJ90ti9FlZX.html) |
| `bd2d2687f424c7750nNy39u5FlZW` | ai软件销售经理（算力） | RAG | [详情页](https://www.zhipin.com/job_detail/bd2d2687f424c7750nNy39u5FlZW.html) |
| `60023e7805336c290nN-3d6-FFFT` | 地理信息科学java后端工程师（民航GIS) | RAG | [详情页](https://www.zhipin.com/job_detail/60023e7805336c290nN-3d6-FFFT.html) |
| `102e7161982e9ff60nN82tS7FlZW` | AI 应用开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/102e7161982e9ff60nN82tS7FlZW.html) |
| `b12a3aad75f507450nB42di6EFJS` | 大模型算法工程师（驻佛山项目） | RAG | [详情页](https://www.zhipin.com/job_detail/b12a3aad75f507450nB42di6EFJS.html) |
| `d61edc46f25177750nJ529i0GVBY` | 座舱音频系统工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/d61edc46f25177750nJ529i0GVBY.html) |
| `1dffe94b054e39170nNy3di5FFJT` | 中/高级AI产品经理 | RAG | [详情页](https://www.zhipin.com/job_detail/1dffe94b054e39170nNy3di5FFJT.html) |
| `ab0b8731435c62900nd43tu9ElpU` | 智能体研发工程师（投研方向） | RAG | [详情页](https://www.zhipin.com/job_detail/ab0b8731435c62900nd43tu9ElpU.html) |
| `e62257cee10c20b20nx72Nu6F1RU` | 安全智能体开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/e62257cee10c20b20nx72Nu6F1RU.html) |
| `0a361b9bc8cbeb870nJ529y_E1ZZ` | 跨境电商AI应用师 | RAG | [详情页](https://www.zhipin.com/job_detail/0a361b9bc8cbeb870nJ529y_E1ZZ.html) |
| `d6f6cc441040d0c10nx43tu_EFNV` | 售前解决方案顾问（AI 企业服务 / 大模型） | RAG | [详情页](https://www.zhipin.com/job_detail/d6f6cc441040d0c10nx43tu_EFNV.html) |
| `099ef78f8e9266da0nx-2960ElpR` | FDE前沿部署工程师 (MJ001077) | RAG | [详情页](https://www.zhipin.com/job_detail/099ef78f8e9266da0nx-2960ElpR.html) |
| `91738acb5e08f58a0ndy0tm5EFVQ` | 大模型算法工程师【13薪/高薪】线上面 | RAG | [详情页](https://www.zhipin.com/job_detail/91738acb5e08f58a0ndy0tm5EFVQ.html) |
| `3bb9669da78034a20nB429S5ElpX` | AI应用交付工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/3bb9669da78034a20nB429S5ElpX.html) |
| `fed4163cedcd52600nx52Nq9F1VZ` | FDE 前线部署工程师（AI应用交付） | RAG | [详情页](https://www.zhipin.com/job_detail/fed4163cedcd52600nx52Nq9F1VZ.html) |
| `9d903adef4ea498f0nN92925F1dS` | ai开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/9d903adef4ea498f0nN92925F1dS.html) |
| `0df86900235378ed0nx42t6_FFFZ` | FDE工程师-AI专场 | RAG | [详情页](https://www.zhipin.com/job_detail/0df86900235378ed0nx42t6_FFFZ.html) |
| `1b29d9797fe318520nJy2dy5GFNW` | AI产品经理（Base:深圳，支持远程办公） | RAG | [详情页](https://www.zhipin.com/job_detail/1b29d9797fe318520nJy2dy5GFNW.html) |
| `9f466960019f782e0nx50tW4EFFU` | RAG工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/9f466960019f782e0nx50tW4EFFU.html) |
| `43bb4aaf55a6a8990nx729i0FlpW` | 安全开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/43bb4aaf55a6a8990nx729i0FlpW.html) |
| `b87a7a61335d1be203xz3dq7FlVX` | AI数据/机器学习工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/b87a7a61335d1be203xz3dq7FlVX.html) |
| `3eebce03264c36520nx50tW5FFVU` | AI架构负责人 | RAG | [详情页](https://www.zhipin.com/job_detail/3eebce03264c36520nx50tW5FFVU.html) |
| `ac98bb24fa17d92f0nN82d65FlpT` | 架构师 | RAG | [详情页](https://www.zhipin.com/job_detail/ac98bb24fa17d92f0nN82d65FlpT.html) |
| `35ac779d5e28ea0e0nJz2Nm1EVVY` | 产品经理 | RAG | [详情页](https://www.zhipin.com/job_detail/35ac779d5e28ea0e0nJz2Nm1EVVY.html) |
| `a0f1836697c8bf710nN-09i5E1BS` | 大模型算法研究员/专家 | RAG | [详情页](https://www.zhipin.com/job_detail/a0f1836697c8bf710nN-09i5E1BS.html) |
| `bdad8c2cbe4768550nN_2ti7ElRU` | 产品经理（母婴智能体方向） | RAG | [详情页](https://www.zhipin.com/job_detail/bdad8c2cbe4768550nN_2ti7ElRU.html) |
| `e056a7f204799b8c0ndz0966EVJW` | 系统架构师(Al智能体方向) | RAG | [详情页](https://www.zhipin.com/job_detail/e056a7f204799b8c0ndz0966EVJW.html) |
| `2d38eff6b310b45e0nNy39q5GVVU` | 首席工程师（AI应用开发） | RAG | [详情页](https://www.zhipin.com/job_detail/2d38eff6b310b45e0nNy39q5GVVU.html) |
| `2a31affad8782c520nx639-4EltY` | 大模型算法工程师 / AI算法工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/2a31affad8782c520nx639-4EltY.html) |
| `687e39edd172bf460nN93N28GVtV` | AI业务工程专家（MJ000200） | RAG | [详情页](https://www.zhipin.com/job_detail/687e39edd172bf460nN93N28GVtV.html) |
| `33ea4b888ebc39840nx5396_FlpT` | 图像算法工程师（AI 图像生成方向） | RAG | [详情页](https://www.zhipin.com/job_detail/33ea4b888ebc39840nx5396_FlpT.html) |
| `4f1911fdbb27b85d0nN53965ElBY` | 高级 / 资深前端开发工程师(A170275) | RAG | [详情页](https://www.zhipin.com/job_detail/4f1911fdbb27b85d0nN53965ElBY.html) |
| `7aeeed59f79d9b170nN80tu4EFpW` | Python AI开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/7aeeed59f79d9b170nN80tu4EFpW.html) |
| `3074cb0a30c6c5ab0nBy2Nu_FVtV` | 商业化AI增长技术专家 | RAG | [详情页](https://www.zhipin.com/job_detail/3074cb0a30c6c5ab0nBy2Nu_FVtV.html) |
| `9a1506e2591cdd4c0nBy0924FlBU` | ERP产品经理（agent方向） | RAG | [详情页](https://www.zhipin.com/job_detail/9a1506e2591cdd4c0nBy0924FlBU.html) |
| `162f72ff6390e9e10nx73dW_FVBZ` | 双美行业AI FDE（产品与体验方向） | RAG | [详情页](https://www.zhipin.com/job_detail/162f72ff6390e9e10nx73dW_FVBZ.html) |
| `0a94fd25fe824dfb0nF409y7F1RU` | 后端开发工程师（广告业务） | RAG | [详情页](https://www.zhipin.com/job_detail/0a94fd25fe824dfb0nF409y7F1RU.html) |
| `f6bc1f8c2b2c30f60nN50t6_FlZX` | AI创新组长 | RAG | [详情页](https://www.zhipin.com/job_detail/f6bc1f8c2b2c30f60nN50t6_FlZX.html) |
| `1550d370f66ed2a30nN429y9FFpU` | 机器学习工程师（AI应用方向）(J10029) | RAG | [详情页](https://www.zhipin.com/job_detail/1550d370f66ed2a30nN429y9FFpU.html) |
| `5b4d8f1f74b397190nN-2tm8E1VW` | AI产品经理 | RAG | [详情页](https://www.zhipin.com/job_detail/5b4d8f1f74b397190nN-2tm8E1VW.html) |
| `b8af0f4092097e4a0nJ-2dq4EVFY` | 商城产品经理 | RAG | [详情页](https://www.zhipin.com/job_detail/b8af0f4092097e4a0nJ-2dq4EVFY.html) |
| `183c05f57364e5a70nx-2921FFJR` | 信息技术岗-【某资产投资单位正编】 | RAG | [详情页](https://www.zhipin.com/job_detail/183c05f57364e5a70nx-2921FFJR.html) |
| `e89659baf7a538911H1_3dy6FFNS` | Java开发工程师-商家后台 | RAG | [详情页](https://www.zhipin.com/job_detail/e89659baf7a538911H1_3dy6FFNS.html) |
| `ca50b127053dac4d0nJ82N25FFJT` | AI运维开发工程师（MLOps方向） | RAG | [详情页](https://www.zhipin.com/job_detail/ca50b127053dac4d0nJ82N25FFJT.html) |
| `23e68b418dab22630nFz0t-4ElFW` | 算法研究员（K12教育方向） | RAG | [详情页](https://www.zhipin.com/job_detail/23e68b418dab22630nFz0t-4ElFW.html) |
| `89e9a790df40bffb0nFy39m5EVtS` | AI应用工程师【资深】 | RAG | [详情页](https://www.zhipin.com/job_detail/89e9a790df40bffb0nFy39m5EVtS.html) |
| `9a50ed44536c43010nx73t61FVpX` | C端-AI应用架构师 | RAG | [详情页](https://www.zhipin.com/job_detail/9a50ed44536c43010nx73t61FVpX.html) |
| `6da386a38bd61d850nF73t-4GVZW` | 大模型开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/6da386a38bd61d850nF73t-4GVZW.html) |
| `b4c532b37c7b3bf803Ny3N25FVVY` | Java系统架构师 | RAG | [详情页](https://www.zhipin.com/job_detail/b4c532b37c7b3bf803Ny3N25FVVY.html) |
| `d26286b0fb6fc5150nN50ty5FVJS` | 大模型训练优化工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/d26286b0fb6fc5150nN50ty5FVJS.html) |
| `a03b59a28dde52360nN82d29GVRR` | AI产品经理 | RAG | [详情页](https://www.zhipin.com/job_detail/a03b59a28dde52360nN82d29GVRR.html) |
| `d7fedf624e6a518c0nF53tS9EFFR` | java全栈开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/d7fedf624e6a518c0nF53tS9EFFR.html) |
| `9846e7859a5e79a70nNy0966F1FZ` | 软件产品经理 | RAG | [详情页](https://www.zhipin.com/job_detail/9846e7859a5e79a70nNy0966F1FZ.html) |
| `230d0928f72370420nJ43N64F1JR` | 平台开发(Java） | RAG | [详情页](https://www.zhipin.com/job_detail/230d0928f72370420nJ43N64F1JR.html) |
| `223e89ec3ba7bbf60nBy09W5ElFY` | 售前解决方案工程师（AI人工智能） | RAG | [详情页](https://www.zhipin.com/job_detail/223e89ec3ba7bbf60nBy09W5ElFY.html) |
| `d44455e3a2a294d70nB-3927ElZR` | 技术总监/架构师（AI大模型应用方向~） | RAG | [详情页](https://www.zhipin.com/job_detail/d44455e3a2a294d70nB-3927ElZR.html) |
| `1c332109bbbb76a70nx409m8F1RV` | GEO负责人 | RAG | [详情页](https://www.zhipin.com/job_detail/1c332109bbbb76a70nx409m8F1RV.html) |
| `8f44852050bb0da70nx73t69GVFT` | AI开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/8f44852050bb0da70nx73t69GVFT.html) |
| `abc830b24846e1960nx609S5FltW` | 售前技术支持 | RAG | [详情页](https://www.zhipin.com/job_detail/abc830b24846e1960nx609S5FltW.html) |
| `1dd04ea92382f7430nFy2928EFBW` | 金融模型算法开发工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/1dd04ea92382f7430nFy2928EFBW.html) |
| `913620393850e6e00nF90969FVVZ` | MLOps 工程师(LLMOps方向) | RAG | [详情页](https://www.zhipin.com/job_detail/913620393850e6e00nF90969FVVZ.html) |
| `61667fc0c0d801680nx7392-GVBQ` | ai应用工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/61667fc0c0d801680nx7392-GVBQ.html) |
| `405f82b01da865490nx53dW8F1tW` | 运维开发工程师（Devops） | RAG | [详情页](https://www.zhipin.com/job_detail/405f82b01da865490nx53dW8F1tW.html) |
| `c8270d6f25b56ad60nJz0ti4E1BT` | 自然语言处理算法 | RAG | [详情页](https://www.zhipin.com/job_detail/c8270d6f25b56ad60nJz0ti4E1BT.html) |
| `daf59d98ddf853da0nx62961FVVV` | 系统架构工程师岗（人工智能平台方向） | RAG | [详情页](https://www.zhipin.com/job_detail/daf59d98ddf853da0nx62961FVVV.html) |
| `87850b97bf82651c0nN80927GFZR` | 算法工程师 | RAG | [详情页](https://www.zhipin.com/job_detail/87850b97bf82651c0nN80927GFZR.html) |
| `b63c6042f471ea8e0nF909u5F1pV` | 数据库内核研发工程师（AP 引擎方向 ) | RAG | [详情页](https://www.zhipin.com/job_detail/b63c6042f471ea8e0nF909u5F1pV.html) |
| `95bbf247e74450da0nZ42d27EldW` | 企微AI应用后台开发工程师-RAG 方向 | RAG | [详情页](https://www.zhipin.com/job_detail/95bbf247e74450da0nZ42d27EldW.html) |
| `3b6c439e8231ab0a0nx42tS9EVNW` | 多模态大模型算法（CV/LLM/AIGC） | RAG | [详情页](https://www.zhipin.com/job_detail/3b6c439e8231ab0a0nx42tS9EVNW.html) |
| `87d8ab412ac8d8b10nR529i1FVRX` | AI解决方案专家（RAG） | RAG | [详情页](https://www.zhipin.com/job_detail/87d8ab412ac8d8b10nR529i1FVRX.html) |
| `b42ea94507e6ee8b0nx63d27GVpQ` | 高级方案经理（国企\|工业数字化/AI方向） | RAG | [详情页](https://www.zhipin.com/job_detail/b42ea94507e6ee8b0nx63d27GVpQ.html) |
| `285da249c381a74e0nx62d-_E1NY` | AI工程负责人 | RAG | [详情页](https://www.zhipin.com/job_detail/285da249c381a74e0nx62d-_E1NY.html) |

## 审计备注

- 原有旧版唯一无正文岗位为 `33ea4b888ebc39840nx5396_FlpT`；此次汇总后无正文岗位 `33ea4b888ebc39840nx5396_FlpT`。
- 被标记“下线”的 204 个岗位保留完整历史正文与链接，以便人工复核或后续恢复。
- GitHub 文件更新本身不会自动将 CSV 状态写入现有数据库中的 `job_status`，也不会刷新数据库索引。
