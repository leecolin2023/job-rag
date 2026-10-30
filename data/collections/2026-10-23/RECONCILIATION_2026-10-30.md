# 2026-10-30 BOSS 岗位字段核验与三份数据修复报告

目标文件：`data/jobs.csv`、`agent.csv`、`rag.csv`。原始采集日期 **2026-10-23**，核验与修复日期 **2026-10-30**。

## 修复统计

| 变更字段 | Agent | RAG | jobs.csv |
|---|---:|---:|---:|
| 公司 | 4 | 20 | 1 |
| 学历 | 7 | 1 | 6 |
| JD 正文 | 27 | 151 | 0 |

共修改 **217 个单元格**，岗位数量不变（Agent 289，RAG 302，主表 593）。所有匹配的职位 ID 在职位名称、公司、地点、薪资、经验、学历、详情链接、JD、采集日期这 9 个字段上已完全一致。

## 校验依据与重要限制

- **公司：** BOSS 详情页上，有猎头岗位同时显示“客户公司”和“发布职位的招聘机构”。原有主表 `company` 有时是前者、有时是后者；本次只补齐快照的“页面未显示”，以及把主表的“爱化身”修正为页面招聘机构显示的“爱化身科技”。**这不能证明现有公司列已经具备统一的公司主体语义。**
- **学历：** 6 个岗位页面直接显示“学历不限”，因此更新主表和相关快照。另有 2 个岗位页面显示“页面不存在”，只能将快照中的无效占位值 `4` 改成“页面未显示”，**并没有核实学历**。
- **JD：** 快照中 Agent 20 条、RAG 149 条 JD 原本为无效占位符 `4`，从主表现有较完整历史文本恢复；另外 8 条有排版差异，对齐为主表历史原文。另 1 条 RAG 快照的 JD 原本为 `4`，但主表也没有 JD，且 BOSS 页面不存在，因此改为空字符串。
- **网页可见性：** BOSS 未登录时显示“登录查看完整内容”，无法逐字校验全部 JD。因此 JD 的恢复属于**基于主表历史信息的数据修复**，不能表述为“全量网页正文已实时核验”。
- **时间与状态：** 页面有岗位显示“职位已关闭”，也有“招聘中”，但主表 `status` 是采集状态而不是招聘状态，不能混写；本次没有修改 `status`、`collected_at` 或运行时数据索引。

## 公司字段逐条变更（网页可见值）

| 数据 | 职位 ID（详情页） | 旧值 | 新值 | 网页对应标签 |
|---|---|---|---|---|
| 主表 | [00107f904fe485a60nx729m6E1VV](https://www.zhipin.com/job_detail/00107f904fe485a60nx729m6E1VV.html) | 爱化身 | 爱化身科技 | 招聘机构 |
| Agent | [00107f904fe485a60nx729m6E1VV](https://www.zhipin.com/job_detail/00107f904fe485a60nx729m6E1VV.html) | 爱化身 | 爱化身科技 | 招聘机构 |
| Agent | [8a5d5bed007d05060nJ429S5F1ZZ](https://www.zhipin.com/job_detail/8a5d5bed007d05060nJ429S5F1ZZ.html) | 页面未显示 | 锐仕方达 | 招聘机构 |
| Agent | [fd1a3d366f85cde60nJ609y9FVdU](https://www.zhipin.com/job_detail/fd1a3d366f85cde60nJ609y9FVdU.html) | 页面未显示 | 米高蒲志(上海)... | 招聘机构 |
| Agent | [727712d88cb166b00nJ92dy8EVpU](https://www.zhipin.com/job_detail/727712d88cb166b00nJ92dy8EVpU.html) | 页面未显示 | 猎高 | 招聘机构 |
| RAG | [92c7ed5d0f77d1e90nx53dq6GVNR](https://www.zhipin.com/job_detail/92c7ed5d0f77d1e90nx53dq6GVNR.html) | 页面未显示 | 杭州某大型游戏上市公司 | 客户公司 |
| RAG | [702e9b55496ff9ea0nx60t6_FFRU](https://www.zhipin.com/job_detail/702e9b55496ff9ea0nx60t6_FFRU.html) | 页面未显示 | 杭州某中型互联网公司 | 客户公司 |
| RAG | [4c27591d7729b1420nx52t60GVBR](https://www.zhipin.com/job_detail/4c27591d7729b1420nx52t60GVBR.html) | 页面未显示 | 某大型游戏公司 | 客户公司 |
| RAG | [4975ecace36038c70nFy39q6GVtR](https://www.zhipin.com/job_detail/4975ecace36038c70nFy39q6GVtR.html) | 页面未显示 | 上海某大型互联网金融上市公司 | 客户公司 |
| RAG | [27dcc1b566f318a50nN_3tW9E1VW](https://www.zhipin.com/job_detail/27dcc1b566f318a50nN_3tW9E1VW.html) | 页面未显示 | 某中型计算机软件公司 | 客户公司 |
| RAG | [eec4199fd295cc480nx739S-FFVS](https://www.zhipin.com/job_detail/eec4199fd295cc480nx739S-FFVS.html) | 页面未显示 | 杭州某中型互联网公司 | 客户公司 |
| RAG | [ae80798c88a78bd70nx53tS_FVpY](https://www.zhipin.com/job_detail/ae80798c88a78bd70nx53tS_FVpY.html) | 页面未显示 | 某小型人工智能公司 | 客户公司 |
| RAG | [8636e441374b9d0c0nB829m6ElBZ](https://www.zhipin.com/job_detail/8636e441374b9d0c0nB829m6ElBZ.html) | 页面未显示 | 广州某大型医疗健康公司 | 客户公司 |
| RAG | [0d6b7fa1fc88231e0nN929q8ElpY](https://www.zhipin.com/job_detail/0d6b7fa1fc88231e0nN929q8ElpY.html) | 页面未显示 | 广州某中型计算机软件公司 | 客户公司 |
| RAG | [0df86900235378ed0nx42t6_FFFZ](https://www.zhipin.com/job_detail/0df86900235378ed0nx42t6_FFFZ.html) | 页面未显示 | 南京爱贤进 | 招聘机构 |
| RAG | [a0f1836697c8bf710nN-09i5E1BS](https://www.zhipin.com/job_detail/a0f1836697c8bf710nN-09i5E1BS.html) | 页面未显示 | 纵横 | 招聘机构 |
| RAG | [e056a7f204799b8c0ndz0966EVJW](https://www.zhipin.com/job_detail/e056a7f204799b8c0ndz0966EVJW.html) | 页面未显示 | 锐仕方达 | 招聘机构 |
| RAG | [2a31affad8782c520nx639-4EltY](https://www.zhipin.com/job_detail/2a31affad8782c520nx639-4EltY.html) | 页面未显示 | 深圳艾思伯 | 招聘机构 |
| RAG | [e7707b9dedc7cec60nV739u6E1VQ](https://www.zhipin.com/job_detail/e7707b9dedc7cec60nV739u6E1VQ.html) | 页面未显示 | 睿隆 | 招聘机构 |
| RAG | [34ad8e7b64699b480nB-29i0FVBQ](https://www.zhipin.com/job_detail/34ad8e7b64699b480nB-29i0FVBQ.html) | 页面未显示 | 金华希睿企业管理咨询 | 招聘机构 |
| RAG | [9a50ed44536c43010nx73t61FVpX](https://www.zhipin.com/job_detail/9a50ed44536c43010nx73t61FVpX.html) | 页面未显示 | 途聚人力 | 招聘机构 |
| RAG | [d44455e3a2a294d70nB-3927ElZR](https://www.zhipin.com/job_detail/d44455e3a2a294d70nB-3927ElZR.html) | 页面未显示 | 睿资达 | 招聘机构 |
| RAG | [daf59d98ddf853da0nx62961FVVV](https://www.zhipin.com/job_detail/daf59d98ddf853da0nx62961FVVV.html) | 页面未显示 | 广州路晟管理咨询 | 招聘机构 |
| RAG | [b42ea94507e6ee8b0nx63d27GVpQ](https://www.zhipin.com/job_detail/b42ea94507e6ee8b0nx63d27GVpQ.html) | 页面未显示 | 三棵榕 | 招聘机构 |
| RAG | [9d3b778a560da9570nF62dq4EltQ](https://www.zhipin.com/job_detail/9d3b778a560da9570nF62dq4EltQ.html) | 页面未显示 | 上海岱澳人才信息咨询 | 招聘机构 |

## 学历字段逐条变更

| 数据 | 职位 ID（详情页） | 旧值 | 新值 | 核验情况 |
|---|---|---|---|---|
| 主表 | [d923816f33cb170b0nR80tu1FlVQ](https://www.zhipin.com/job_detail/d923816f33cb170b0nR80tu1FlVQ.html) | 页面未显示 | 学历不限 | 网页明确显示学历不限 |
| 主表 | [e2d8eec16923ffdc0nNz2ty0E1JR](https://www.zhipin.com/job_detail/e2d8eec16923ffdc0nNz2ty0E1JR.html) | 页面未显示 | 学历不限 | 网页明确显示学历不限 |
| 主表 | [6bb7e60b51b853e50nNy3Nq_GVFW](https://www.zhipin.com/job_detail/6bb7e60b51b853e50nNy3Nq_GVFW.html) | 页面未显示 | 学历不限 | 网页明确显示学历不限 |
| 主表 | [ad28eca6d4e69d370nF43dm0FVNQ](https://www.zhipin.com/job_detail/ad28eca6d4e69d370nF43dm0FVNQ.html) | 页面未显示 | 学历不限 | 网页明确显示学历不限 |
| 主表 | [82b21269e044e57b0ndy3d60F1VY](https://www.zhipin.com/job_detail/82b21269e044e57b0ndy3d60F1VY.html) | 页面未显示 | 学历不限 | 网页明确显示学历不限 |
| 主表 | [bfcf52715d6d83ab03F83dm9E1NX](https://www.zhipin.com/job_detail/bfcf52715d6d83ab03F83dm9E1NX.html) | 页面未显示 | 学历不限 | 网页明确显示学历不限 |
| Agent | [37bf3f6943fb53fa0nN909i6E1BS](https://www.zhipin.com/job_detail/37bf3f6943fb53fa0nN909i6E1BS.html) | 4 | 页面未显示 | 网页已不存在，只规范缺失标记 |
| Agent | [d923816f33cb170b0nR80tu1FlVQ](https://www.zhipin.com/job_detail/d923816f33cb170b0nR80tu1FlVQ.html) | 4 | 学历不限 | 网页明确显示学历不限 |
| Agent | [e2d8eec16923ffdc0nNz2ty0E1JR](https://www.zhipin.com/job_detail/e2d8eec16923ffdc0nNz2ty0E1JR.html) | 4 | 学历不限 | 网页明确显示学历不限 |
| Agent | [6bb7e60b51b853e50nNy3Nq_GVFW](https://www.zhipin.com/job_detail/6bb7e60b51b853e50nNy3Nq_GVFW.html) | 4 | 学历不限 | 网页明确显示学历不限 |
| Agent | [08030772d7dcc25f0nx50ti0FFVW](https://www.zhipin.com/job_detail/08030772d7dcc25f0nx50ti0FFVW.html) | 4 | 页面未显示 | 网页已不存在，只规范缺失标记 |
| Agent | [ad28eca6d4e69d370nF43dm0FVNQ](https://www.zhipin.com/job_detail/ad28eca6d4e69d370nF43dm0FVNQ.html) | 4 | 学历不限 | 网页明确显示学历不限 |
| Agent | [82b21269e044e57b0ndy3d60F1VY](https://www.zhipin.com/job_detail/82b21269e044e57b0ndy3d60F1VY.html) | 4 | 学历不限 | 网页明确显示学历不限 |
| RAG | [bfcf52715d6d83ab03F83dm9E1NX](https://www.zhipin.com/job_detail/bfcf52715d6d83ab03F83dm9E1NX.html) | 4 | 学历不限 | 网页明确显示学历不限 |

## 缺失正文

无可用 JD 的职位：`33ea4b888ebc39840nx5396_FlpT`（图像算法工程师（AI 图像生成方向））。主表为空、RAG 快照从 `4` 规范为空，且链接返回“页面不存在”。应从技术要求统计中排除，不能将缺失正文解释为“没有技术要求”。

## 后续建议

若要真正统一“公司”字段，应拆分 `client_company`（实际用人单位）与 `recruiter_company`（职位发布方）并重新校验。日后支持登录后采集全文，可把已登录采集文本作为新的版本，保留本次历史来源和差异记录。
