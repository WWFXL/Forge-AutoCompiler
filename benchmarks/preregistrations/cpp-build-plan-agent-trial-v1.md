# 初始构建方案与恢复 Agent 小规模试运行 v1

身份：`cpp-build-plan-agent-trial-v1`。跟踪：[Issue #469](https://github.com/WWFXL/Forge-AutoCompiler/issues/469)。

## 研究阶段与问题

本阶段为真实模型接入的探索性试运行，不是正式效果比较。问题是：模型能否依据限定源码生成可执行方案，在 Workflow 交接后返回合法修订，并在固定验证与干净重建下完成交付？不研究新选择器、动态预算策略、成功率非劣或成本节省。

`#468` 已通过脚本化方案执行工程验证；本轮复用其本地未提交原型，不声称它已成为发布版本。`#463/#465/#467` 停止决定与全部冻结 evidence 保持只读，不续跑或补齐。

## 固定样本与两条路径

仅使用已经走读过的 cJSON，commit `c859b25da02955fef659d658b8f324b5cde87be3`，源码 tar SHA-256 `26da701f2cb689e042361a4bd8904595f2fa41409812e781fc8759ed54a0f734`。它是开发样本，不是未见 holdout。

镜像固定 `sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`，2 CPU。验证由任务作者固定：在 `build` 目录运行全部 19 项 CTest，指定输出依据和 LastTest.log。交付只要求 `libcjson.so.1.7.19`，不是完整安装包。

1. 初始规划：Agent 只看当前源码、任务与剩余预算，读 README/CMake/测试配置等后返回完整步骤。不给上轮成功方案、历史实验报告或个人知识库。
2. 正常路径：新 Compile Session 执行模型方案；失败时最多两次交接，Agent 返回完整方案建议，Workflow 执行。成功须通过既有 submit、指定测试、clean replay 和 cleanup。
3. 受控恢复路径：仅在正常路径成功后，用同一初始模型方案在另一个全新 Session 开始。人为把首条 build 命令替换成 `cmake --build build --parallel 2 --target forge_trial_missing_target`，触发真实命令失败；Agent 查看交接与失败日志后建议修订。该故障明确标记为受控测试，不能列入自然失败数据。

两条路径共用一次初始模型规划。第二条初始方案来自模型，但错误 target 由 runner 注入；不能称为完全自主发现的自然错误。模型恢复会话重新建立，不继承正常路径的恢复对话。

## Agent 与 Workflow 权限

复用 LangChain `create_agent()` 和 `ToolStrategy`；Agent 只有列源码、读源码、恢复时读限定日志三类只读工具。读取限源码根或 Session 的 logs/replay，拒绝越界路径，保留读取哈希与截断标记。

输出为 `PlanProposal(reason, steps)`。任务身份、源码、镜像、交付及验证由 `PlanTask` 固定，不能由模型替换。Workflow 独占容器、执行命令、核对交接、让受影响步骤记录失效并生成成功配方。模型不直接使用 Shell，不自行写入 Session 或宣告成功。

这是“提出修订，由 Workflow 执行”的恢复 Agent，不是具备任意终端访问权的工具型 Compiler Agent。当前试运行不回答后一种 Agent 的上限。

## Provider 与预算

- Provider：DeepSeek 官方 `https://api.deepseek.com`；请求模型 `deepseek-v4-pro`，thinking enabled；返回标识只接受 `DeepSeek-V4-Pro-0813` 或 `deepseek-v4-pro`。别名不是模型权重身份保证。
- 全阶段最多 **12 次物理模型请求**，包括初始规划与两路径的全部恢复；SDK retries=0，结构化方案错误不自动补问。
- 全阶段 recorded Token 请求准入阈值 **150,000**，单响应上界 **50,000**，派生授权上界 **200,000**。完成响应先完整记录 usage，再判断阈值；响应超过上界也保留实际计量并停止，不截断回填。
- 每请求最多输出 8,192 tokens，timeout 120 秒；消息 JSON 上下文上限 60,000 bytes。模型及框架的工具 schema 额外占用上下文，响应总量以上游真实 usage 为准；缺失或不一致时停止，不能假设为 0。
- Agent 请求与读取共用最多 24 次工具调用、36 步、1,200 秒准入时间预算。每条路径另有 32 条 Workflow 执行命令、2 次交接、600 秒、单命令 120 秒；diagnostic 10 秒、clean replay 180 秒及既有清理独立时限。不是统一动态预算优化。
- Provider 估算费用总上限 **2 美元**；按峰时 cache-miss 输入 `$1.32/M`、输出 `$3.96/M` 保守计价，并为下一完整响应预留费用。来源：[DeepSeek Pricing](https://api-docs.deepseek.com/quick_start/pricing)，2026-10-19 核对。估算不等于实际账单；不把缓存/时段折扣算作方法收益。

准入预算不能取消已经发出的请求；如果 Provider 违反单响应上界，保留完整观察并停止，不能宣称实际费用/Token 仍满足预算。不能为了完成路径增加请求数、重试、扩样本或放宽验证。

## 授权与停止

用户已授权进入本阶段的本地实现与验证；**当前候选协议本身不包含 Provider 支出授权**。真实凭据读取和调用前，需要用户明确确认以上模型与最多 2 美元的试运行。CLI 要求独立授权 JSON 精确匹配协议 SHA-256；没有授权只允许运行 `--validate-only`。不修改应用配置或打印凭据。

出现以下任一项即停止该试运行，保留已完成和失败记录：初始方案非法、任务/模型/组件身份不匹配、usage 缺失或不一致、请求/Token/费用/时间预算不足、不可恢复或无法合法修订、验收/cleanup 未闭合。正常路径未完成则不运行第二条路径。一次 create-once 输出目录，不在同一身份重新运行挽救。

若初始方案直接成功，说明这一开发任务的规划可用；若受控恢复成功，只说明本设置下模型与控制链路闭合。失败按输入、Provider、格式、计划合同、命令、验证、预算、cleanup 分类，不自动解释为方法或模型能力负结果。

## 核验与证据

运行前核对候选 manifest、本文、所列代码哈希、源码归档、镜像可达与零调用测试。实际运行输出至新的独立目录，先保存协议、授权、模型请求/原始响应/读取工具记录，再保存各 Session、方案版本、失败日志、结果及 replay。

原始模型响应在结构化解析前记录 usage，框架合成 ToolMessage 不作为新的模型响应计量。方案解析失败也保留已发生的真实请求及费用。未知/失败用量不得填成 0。

报告分开列初始规划质量、正常路径交接、受控故障恢复、指定测试、独立重建、cleanup 与真实用量。零调用夹具的“模型请求”是脚本化响应计数，不记为真实 Provider 请求。

本试运行不包含项目族隔离、重复性或匹配基线，不能报告自然失败成功率、跨系统泛化、选择器增益、显著性或论文创新点已成立。后续是否增加项目/构建系统或设计对照，由观察结果与研究负责人另行决定。

实现选择参考：[LangChain Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output) 与已安装的类型/文档；沿用项目已有依赖，不引入新的 Agent 框架。
