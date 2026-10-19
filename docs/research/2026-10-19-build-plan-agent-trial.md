# 构建方案生成与恢复 Agent 接入记录

日期：2026-10-19。Issue：[ #469](https://github.com/WWFXL/Forge-AutoCompiler/issues/469)。工作类型：基础设施、接线修复与探索性试运行。

## 当前结果

**最新：用户进一步授权继续修复后，独立repair campaign已完成真实规划、正常构建、受控错误target恢复、19项CTest、clean replay及cleanup。** 全部失败均保留，完整结果和累计用量见[修复完成报告](2026-10-19-build-plan-agent-repair-results.md)。下文保留v1/v2的原始失败及分析，不是当前阻塞状态。

Agent 与 Workflow 的接入已实现，并通过零 Provider 工程验证。真实 v1 在首个 Provider 请求因 BadRequestError 停止，未产生方案或构建 Session；已按协议封存，不重试。这不是研究方法或模型构建能力的负结果。

独立 v2 经用户明确授权后执行，收到一次真实 thinking 响应，随后因源码读取路径契约不一致停止；未生成方案或创建构建 Session，没有重试。v2已封存并通过只读审计。本轮确认接口能返回响应，同时暴露工具接线缺陷，仍未进入真实构建/恢复能力检验。

## 实现与验证

- `plan_agent.py`：复用 LangChain create_agent 与 ToolStrategy；只读列目录/源码/日志工具，输出完整 PlanProposal。
- `PlanTask` 固定源码、镜像、交付与测试，Workflow 执行方案并处理交接/失效/既有验收；模型没有直接 Shell 权限。
- 模型原始响应在结构化解析前保存并记录 usage，非法结构化输出也计量；框架合成的 ToolMessage 不计作新的模型响应。
- `plan_agent_v2.py`：仅为本试运行提供 auto tool choice 的独立 DeepSeek 适配器，不改共享 provider 或 v1 代码；补充安全的错误体诊断字段，未知费用显示为未知。
- `forge_build_plan_agent_trial*.py`：候选协议/代码/源码/授权哈希校验，独立进程、全新输出目录与既有 Docker 验收；不替换默认产品入口。

验证结果：相关回归 **208 passed, 1 skipped**；真实 Docker 脚本化 Agent 接线夹具 **1 passed**，完成两个独立 Session 的编译、故障交接、修订、clean replay 和 cleanup。另有真实 SDK MockTransport 测试核对 outgoing 参数、结构化返回、计量及400错误无重试。它们都没有调用 Provider；夹具中的模型响应计数不能当作实际模型能力数据。

## v1 实际观察

用户明确授权 DeepSeek Pro thinking、cJSON 正常/受控恢复两条路径、最多12次请求、Token准入150000/单响应50000/派生上界200000、估算费用最多2美元、无自动重试。

实际只有1次请求开始，随后 BadRequestError；0次完成响应、0次读取工具、0个输出方案、0个构建 Session，正常与受控恢复两条路径均未执行。决定为 `stop_before_build_for_provider_bad_request`。

原 `result.json` 的 Token/费用0是“已有完成响应”的累计值，**不代表已核实的零用量/零费用**。失败请求没有 usage，无法完整核对计量；解释中保留 unknown_usage_requests=1，不修改原始 result 或回填结果。

v1 未保存 Provider 错误正文，故不能还原具体错误文本。零调用排查发现确定的不兼容请求：已安装 LangChain ToolStrategy 绑定 `tool_choice=any`，SDK实际发送 `required`；DeepSeek官方文档明确说明 thinking 模式不支持 required/named tool choice，会返回400。该缺陷与观察一致，但未排除其他400原因。

v1 运行前还修正了 SDK 参数别名：`api_base` 改为已安装模型类型声明的 `base_url`；这是凭据读取/首次请求前的工程修复，不是失败身份重试。早期门禁源码快照和最终运行协议分别保存，没有冒充同一版本。

## v2 修订边界

v2 保留原任务、模型、thinking、只读权限、验证要求和两条路径，只修复工具选择并补足失败计量。v1保持只读，不在原身份重跑。

v2最多11次请求，使累计最多12次。v1未知请求按原单响应上界预留50000 tokens，v2准入阈值下调至100000、单响应50000、派生上界150000；含预留的设计上界仍200000。累计费用上限仍2美元。预留是保守预算设计，不是测量或实际账单。

原 v1 已触发用户同意的停止规则，v2需独立确认；用户已明确回复“同意，按 v2 继续，累计费用上限仍为 2 美元”。任何新的 Provider/计量/预算/验收错误仍按协议停止，不自动派生v3。v2 若完成，也只能说明这一个已见开发项目上的接线与受控恢复闭合。

## v2 实际观察与失败分析

一次真实请求完成，返回模型标识 `deepseek-v4-pro`，usage为1,327 input、383 output、1,710 total tokens，按冻结峰时价格保守估算 **$0.00326832**，无未知用量。v1仍有1次未知请求；不能用v2完整计量掩盖v1缺口，也不能把两次身份合并为成功率统计。v2估算加v1的$0.198预算预留为$0.20126832，预留不是实际费用。

原始响应提出4次读取：列出 `/workspace/repo`，读取该路径下的 README.md、CMakeLists.txt、tests/CMakeLists.txt。实际启动2次工具，均被 `_inside()` 以 `PlanContractError` 拒绝；后两次没有启动记录。0次工具完成、0个合法方案、0个构建 Session、0条构建命令，正常与受控恢复路径均未运行。决定为 `stop_before_build_for_source_tool_path_contract`，没有重试。

零 Provider 事后复现4项：`list_source('.')`和`read_source('README.md')`成功，使用上述容器绝对路径则被拒绝。当前安全边界拒绝绝对路径是预期行为；接线问题在于源码工具描述未明确规范相对路径，而system prompt给出“使用 /workspace/repo 和 /artifacts 容器路径”，没有区分读取工具与执行方案的路径。异常直接传播，使模型不能收到可纠正的工具错误再继续。该解释由冻结代码、真实工具参数和离线复现共同支持，不把它称为模型不能构建项目。

本次未修改v1/v2运行依赖。建议下一步先做零费用工程修复：明确源码根相对路径和Session根相对日志路径，提供调用示例；将可纠正的路径输入错误以有界工具结果反馈，继续拒绝实际越界读取并保留预算/身份等硬停止。以本次真实工具参数验证错误反馈与后续相对路径读取，再决定是否建立新试运行。此处只是后续方案，不自动创建v3或追加Provider请求，也不降低固定测试与clean replay验收。

v2封存为238 files / 2,424,212 bytes，inventory canonical SHA-256 `6e0dbaef40b1d28ed986ab75f523498adc639022cb3098557e71fa7e571be59f`。独立只读审计`valid=true`，校验全部文件、运行组件、授权、请求/响应/usage/费用、工具事件及零构建会话；v1完整inventory未变，0匹配容器。四项复现不调用模型，也不计入真实实验结果。

## 证据位置

- 零调用门禁、只读核验、源码快照、公开接口文档快照与授权：`/home/yiwei/.codex/outputs/forge-build-plan-agent-integration-2026-10-19/`。
- v1：`/home/yiwei/.codex/outputs/forge-build-plan-agent-trial-v1/`；含运行协议、授权、首次请求、事件、结果与按运行哈希核对的代码快照。
- v1 封存：234 files / 2,408,734 bytes；inventory canonical SHA-256 `1bdce346628cc594fd6acd1acf756f4aa6307e9c06934b679e9afec69c24c115`。
- v2：`/home/yiwei/.codex/outputs/forge-build-plan-agent-trial-v2/`；含协议、独立授权、请求/响应、事件、结果、源码和运行组件快照、inventory与seal。
- v2外部只读审计与事后复现：integration目录下的`v2-readonly-audit.json`、`v2-path-contract-reproduction.json`；不往已封存原始目录追加分析。
- 协议：`benchmarks/preregistrations/cpp-build-plan-agent-trial-v1.md`、`cpp-build-plan-agent-trial-v2.md`；各自 candidate manifest 绑定运行组件和授权。

前序走读、#468原型以及停止的#463/#465/#467均保持原有证据和结论，不把本轮失败追加进其分母。个人知识库只用于科研助手恢复状态，没有进入实验 Agent 上下文。

参考：[LangChain Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output)、[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)、[DeepSeek Pricing](https://api-docs.deepseek.com/quick_start/pricing)，2026-10-19核对。
