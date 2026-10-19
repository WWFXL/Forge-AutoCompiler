# 三系统受控错误的零模型强规则恢复结果

Issue #516 / PR #517；身份`cpp-build-rule-recovery-qualification-v1`，运行release`ffdcf98ec15a872e4eeac9ff89f00648e97f2306`，manifest SHA-256 `74d131677af531b6f3656a47b46d96ca0cdb70140258c165f90276e6c518b7ce`。这是观察#506模型修订后的开发资格：相同miniz/pigz/libite、人工初始方案及受控错误，各一次，不补跑，不是holdout或公平效果比较。

## 观察结果

| 项目/系统 | 真实初始失败 | 确定性修订 | 保留前缀 | Shell | 严格终点 |
| --- | --- | --- | --- | ---: | --- |
| miniz / CMake | 显式target不存在，exit2 | 删除日志明确指出的单一target | configure | 5 | completed |
| pigz / Make | CC覆盖的编译器不存在，exit2 | 删除CC覆盖，使用冻结镜像默认工具链 | 空 | 4 | completed |
| libite / Autotools | ./configure不存在，exit127 | 源文件证据齐全时将bootstrap noop换为./autogen.sh | 空 | 7 | completed |

3/3 strict completed，全部一次handoff、revision2，合计16条Shell，0凭据读取、0模型请求、0Token、0Provider费用、0未知用量。固定完整测试、原源码文件不变、精确交付、clean replay及cleanup均通过。miniz复用未变configure；libite即使旧bootstrap noop成功，也因首变化点而失效。失败动作及失效旧命令不进入最终replay。

规则接口只接收坏方案、实际handoff与源码文件名，不接收正确参考或#506模型修订；人工正确参考只构造最初坏方案。三个`qualification.rule_revision`事件分别为`remove_missing_explicit_target`、`use_image_default_compiler`、`execute_project_bootstrap_instead_of_noop`；没有任何model请求事件。超时、旧plan hash、错误日志不匹配、源文件证据不齐均拒绝规则，不能据此声称一般安全性。

## 封存与验证

raw `/home/yiwei/.codex/outputs/forge-rule-recovery-qualification-v1/`，1409普通文件/40链接/36515585 bytes，inventory `30b2117f520d571a293f2c9f082d6182786ce44d4d944e3964bc049e6d2e5f27`。独立stdlib审计`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/rule-recovery-v1-audit.json`：valid=true、issues=[]，检查全部65组件与typed inventory、源归档/原文件、逐请求计量、实际初始失败、固定任务与测试、首变化前缀/后缀失效、最终replay及Docker实际清理。运行进程exit0。

九项针对性测试及Ruff/format通过。结果发布仅在最终head的backend-unit-tests、frozen-benchmark-tests、frozen-stage-c-tests三项实际CI全SUCCESS后合并；不绕过分支保护。

## 结论与下一步

本阶段证明这三条已见简单受控失败可以由有界规则端到端闭合。它们不再能作为语义/学习选择器的独有收益证据。规则是观察模型输出后设计，且本阶段收窄了节点300秒、命令120秒、evaluator/replay各180秒、cleanup120秒；与#506资源不同，不能比较成功率/成本因果、非劣、规则优于模型或自然失败恢复率。两个阶段分别保持各自冻结证据，不合并分母。

主线不变。下一阶段先做既有主张与未来对照设计：强规则必须纳入基线；新增状态选择器先证明同源状态下存在合理动作分歧，再冻结公平协议；不为凑创新点增加组件。RQ1仍比较完整路径的成功与全部成本，不能用请求下降概括低成本。RQ3保留验证缺口的分层实证，不把受控拒绝变成自然误接受率。该安排服务硕士论文可答辩的领域方法和系统实证，不要求今夜写论文正文。

本阶段零新增模型支出，共享已知保守估算仍$5.80615200，另旧live未知费用预留$1，预算占用$6.80615200；均不是账单。UTC22:00后不再准入付费新臂，UTC22:45后仅清理交接，UTC23:00绝对停止。
