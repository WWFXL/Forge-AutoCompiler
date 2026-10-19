# 构建方案 Agent 接线修复试运行 v2

身份：`cpp-build-plan-agent-trial-v2`。Issue #469。v1 已于首个请求因 Provider BadRequestError 停止并封存，无规划输出、无构建 Session、无重试。

v1 来源与设计见 [v1 协议](cpp-build-plan-agent-trial-v1.md)。样本、任务、镜像、thinking 模型、只读工具、固定 smoke/交付、正常与受控恢复两条路径、成功判据和停止规则完全相同。v1 不能恢复执行或计入成功分母。

## 修复与证据

离线核对已安装 LangChain factory 和 SDK HTTP 序列化，发现 ToolStrategy 自动设置 `tool_choice=any`，SDK 实际发送 `required`。DeepSeek [Chat Completions 官方文档](https://api-docs.deepseek.com/api/create-chat-completion) 明确说明 required/named tool choice 不支持 thinking，会返回400。

v2 使用独立 `PlanThinkingDeepSeek` 适配器，把该试运行中的强制工具选择转换为 `auto`；保留原结构化 schema、Pydantic 校验、thinking 和固定任务验证，不修改共享模型适配器或 v1 运行代码。工具的实际调用仍由模型选择；未返回合法方案则受原停止规则约束。

新增错误体字段记录与已完成响应用量/未知请求用量区分。SDK MockTransport 测试检查真实 HTTP 请求参数、400错误与不重试，以及真实 SDK + LangChain 图能接收 auto 结构化输出并只计量一次。均为零 Provider 工程测试。

v1 未保留具体错误正文，因此不能断言已排除其他400成因；v2实际兼容性仍需新试运行核验。v1 的 recorded_tokens/cost=0 仅为已完成响应累计值，1个失败请求的 usage 和费用保持未知，不能回填为0。

## 累计预算与新授权

v2 最多11个请求，使 v1+v2 总请求上限仍为12。为 v1 未知用量按原单响应上界预留50,000 tokens，v2 请求准入阈值下调为100,000、单响应上界50,000，v2派生授权上界150,000；含预留累计不超过原200,000设计上界。预留不是测得用量；不能据此宣称已经核实实际累计费用。

Provider估算累计支出仍不超过2美元，不增加原上限。按原峰时最高单价为v1未知请求预留0.198美元；v2自身Token预算对应最高0.594美元，因此在单响应合同成立时保守累计预算不超过0.792美元。若Provider违反单响应上界则完整记录并停止。未知实际账单仍须与费用估算分开。

每次请求超时120秒、输出8192tokens、零SDK重试；其余命令、交接、诊断、replay与cleanup时限沿用v1。v2若遇到Provider错误、非法方案、usage/身份漂移、预算耗尽或验收失败同样立即停止，不再自动派生v3。

v1触发了用户已同意的停止规则，**当前只准备v2候选和零Provider门禁，真实调用需用户明确同意按这一独立修订身份继续**。授权JSON精确绑定v2协议哈希；新目录create-once，运行前复核v1 seal与全量inventory，确保旧失败未被改写。

v2对v1的预算预留和串行接线修复不形成方法收益，也不能将两次身份合并为重复试验或成功率统计。下一决策仍是先观察真实规划/恢复与可复现交付是否闭合，再考虑更大范围研究。
