# Forge 硕士论文阶段初稿

日期：2026-11-11；版本：v0.11恢复Harness结果待审稿；本轮跟踪：[Issue #735](https://github.com/WWFXL/Forge-AutoCompiler/issues/735)。

本版按用户批准纳入E55的18项目、36次H0/R2比较，重点新增第5章5.3.3和第6章6.5.15–16。论证顺序为：状态感知执行→规划优化发现恢复成本转移→结合真实轨迹与系统实现生成R2→配对比较及flex/stderred/sxhkd机制分析。R2完成18/18、H0完成17/18，费用高7.3%、时间高23.6%；局部恢复降本与整体投入同时呈现。摘要、绪论、结论和附录I同步更新。相关正文删减仅作防御的重复表述，实验条件、失败原因和费用定义保留。

本版留待用户审阅，不自动合并为最终论文。原始实验、运行报告及旧版导出保持不变。阅读副本目录：`/home/yiwei/.codex/outputs/forge-thesis-recovery-r2-2026-11-11/`，文件前缀`Forge-硕士论文阶段初稿-v0.11`。Word/PDF/HTML/Markdown已实际导出，PDF 108页、62表12图；已核对36行比较数据、附录18项目源码版本及第86–88页结果布局。取数与导出收据见同目录`export-verification.json`。

暂定题目：**面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究**。

本目录是按章维护的论文真源，沿用七章框架。以下v0.10及更早内容为历史版本记录。v0.10补入[E52第二轮36次比较](../research/2026-11-09-offline-harness-round2-results.md)：十二项目各一次×H0/H1/H2，主产物/文件交付均12/12，最终验证11/12、11/12、10/12；H2初始费低18.2%但总费高87.5%（相对H0），保留H0默认。四次后续未通过及分层解释完整保存。第4章另补共同执行/观察机制，不计候选收益。下文v0.9/v0.7为历史导出统计。v0.9补入一次真实离线提案与24次H0/H1比较，主任务10/12与11/12，H1在线费用高32.9%、时间高18.4%，暂不默认采用；三次共同观察失败保留。v0.8设计稿继续保留。v0.7补齐E42–E50的系统演进、规划路由、两层经验、简洁主构建54次比较及八个真实阶段—动作案例，更新中英摘要、方法图、结果表、结论和附录。当前为导师审阅用阶段稿；学校正式模板、个人信息和最终文献格式仍待完成。

新增设计与入口见[本轮准备记录](../research/2026-11-09-offline-harness-preparation.md)；v0.8阅读副本在`/home/yiwei/.codex/outputs/forge-thesis-offline-harness-2026-11-09/`，已实际导出Word/PDF/HTML/Markdown，PDF 96页，50表11图；统计及文件哈希以build-summary.json和export-verification.json为准。下文v0.7统计属于原阅读稿，不能移作v0.8统计。

首轮[E51结果报告](../research/2026-11-09-offline-harness-round1-results.md)及[24行分析](../../benchmarks/analyses/offline-harness-2026-11-09/slots.csv)为新增取数入口。v0.9阅读副本输出至`/home/yiwei/.codex/outputs/forge-thesis-offline-harness-results-2026-11-09/`，Word/PDF/HTML/Markdown均已实际导出：99页PDF、53表11图、正文约5.58万汉字；新增结果页与数字核验通过，统计/来源/文件哈希见同目录build-summary.json和export-verification.json。

v0.10阅读副本输出至`/home/yiwei/.codex/outputs/forge-thesis-offline-harness-round2-2026-11-09/`，Word/PDF/HTML/Markdown均已实际导出：106页PDF、57表12图、正文约5.90万汉字；第二轮结果数字及第82/84页图表布局已核验。统计、来源和文件哈希见该目录build-summary.json与export-verification.json。各格式由同一分章真源生成，不覆盖旧v0.9。

## 阅读入口

- [七章目录](CONTENTS.md)及`chapters/`：内容修改真源。
- [正文—证据映射](EVIDENCE_MAP.md)：每张结果表的实验身份、分母、报告与边界。
- [主构建系统54次报告](../research/2026-11-05-main-system-results.md)：本版核心主表、6/12分层、全部费用及长尾解释。
- [八个轨迹案例](../research/2026-11-05-state-action-case-analysis.md)：成功、有限规则、Agent恢复、接口缺口与测试未注册；与原实验重叠，不另计样本。
- [论文证据总索引](../research/THESIS_EVIDENCE_INDEX.md)与[待补清单](TODO.md)：完整历史数据及后续收束。

阅读副本位于`/home/yiwei/.codex/outputs/forge-thesis-main-build-2026-11-05/`，文件前缀`Forge-硕士论文阶段初稿-v0.7`，包括Word、PDF、HTML、Markdown。已实查93页PDF、49表11图、正文约5.19万汉字；新增主流程、系统/分层表和案例页已阅读核验。表题随表格末行、简短表格整体和案例单行避免跨页拆开。统计、来源和文件哈希以同目录`build-summary.json`、`export-verification.json`为准。各格式来自同一正文，不维护多份真源。

## 当前完成范围

| 部分 | v0.11内容（保留既有基础） |
|---|---|
| 摘要与第1章 | 构建领域问题、阶段状态动作方法、两层经验及实际结论；不称通用机制首创 |
| 第2章 | 自动化构建、Agent、Harness与经验相关工作；保留正式著录待补项 |
| 第3章 | 任务/阶段/观察建模，历史完整任务与main-build-v1分开，新增实际主构建流程图3-2 |
| 第4章 | 状态观察、有限直接动作、Agent修订、变化后缀、独立工具局部恢复；补充共同执行与观察语义；Jev仅接口实现与中断边界 |
| 第5章 | 经验提炼与来源、一次任务检索、条件建议、精确成功方案、任务后更新；两轮规划提案及结合实现的R2恢复指导 |
| 第6章 | E30/E33历史系统、E01/E02/E04组件、E34恢复、独立经验比较；E45–E48及E50主表7/8、图6-1；E51表30/31/32；E52表33/34/35、图6-8；E55表36/37/38、原案例表39 |
| 第7章 | 依版本总结正向、负向、费用/时间取舍与局限 |
| 附录 | 实验身份、真实角色/提示/工具、参数、E50九项目版本及E52十二项目和E55十八项目及运行参数 |
| 学校格式与个人信息 | 正式模板、封面、声明、作者/导师和致谢待补，不推断填写 |

E50各18次主任务基础/经验/强工具为18/18、18/18、17/18，在线费0.1638351/0.0777816/0.4149729美元；精确复用六次零模型且实际重建，时间比基础低12.1%。基础比强工具费低60.5%、时间高42.2%；经验总体时间差96.3%集中double-conversion，强工具一次提交/清理工具异常保留，不作编译能力排名。一次全归历史获取及制库时经验0.1880090美元仍高于基础在线，不隐去部署成本。

## 编辑与导出

```bash
python3 docs/thesis/tools/build_draft.py \
  --version v0.11 --date 2026-11-11 \
  --output-dir /home/yiwei/.codex/outputs/forge-thesis-recovery-r2-2026-11-11 \
  --deps-dir /home/yiwei/.codex/outputs/forge-thesis-draft-2026-11-02/.doc-libs
```

PDF由LibreOffice从Word转换。新图由`tools/render_main_workflow.py`和`scripts/plot_main_system_results.py`生成PNG/SVG/PDF；其余图保留对应历史脚本。导出不调用Provider，不为写作重新运行编译或产品全测。修改章内容后重新生成目录与阅读副本；第6章表格已按出现顺序统一编号，历史各版旧编号保留在原导出中。

## 历史稿与结论边界

v0.6保留在`forge-thesis-two-level-2026-11-04`（77页PDF、39表9图），对应E40/E41；v0.5保留在`forge-thesis-transfer-action-2026-11-03`（66页、33表6图）；v0.4.1/v0.4分别保留在`forge-thesis-task-action-2026-11-03`与`forge-thesis-conditioned-experience-2026-11-03`，更早版本亦不覆盖。

完整作者测试的旧实验与新主构建范围不同，不由跨批差值推修复因果。E49首次Jev权限拒绝且用量未知，没有语义选择响应，不能作为Jev有效或无效的证据。新状态/恢复效果依原消融，不由整体系统表倒推。原结构化经验、短动作经验、逐条选择与库更新有独立正反结果；精确复用不等于跨版本泛化，新方案保存不等于持续学习。

RichLab历史请求gpt-6-astra、响应gpt-5.6已披露，不能证明实际后端身份或更强模型效果。CXX社区实现只保留原实验参考，本轮没有重跑或声称胜过论文原版。私人知识库只供科研恢复、经MCP维护，不注入构建Agent。
