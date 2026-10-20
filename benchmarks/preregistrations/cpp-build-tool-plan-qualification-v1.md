# cpp-build-tool-plan-qualification-v1

Issue #540；本轮为工具方案基础设施与零Provider工程资格，不是策略效果实验。用户于2026-10-20要求进入资格验证并参考CXXCrafter/CompileAgent。本次授权范围不含任何新增Provider调用或凭据读取，费用为0；旧20美元窗口不复用。

## 前瞻固定

- 顺序：buffer、uncrustify、libverto，均为#532登记的已见开发项目，原精确commit/源码归档/镜像/交付/固定完整验证不变。一次生成、一次执行；不按结果替换或重试，不消费正确参考方案。
- 模块`deerflow.compile.tool_plan`只接收PlanTask和原始源码目录，不接收项目名称、人工配方、历史结果。只生成单根Make/CMake/Autotools模板，按同名唯一ELF/ar文件进行显式可重放暂存。
- 固定测试系统装入，所有字段保持；不以其内容推导额外开关。源码入口冲突/不支持、任务系统不符、已有同名产物、交付源歧义均拒绝。未知依赖不猜包名、不在生成阶段执行源码。
- 复用CanaryWorkflow及严格验证；实际失败保存原handoff并抛ToolPlanNeedsAgent，停止该项，不调用模型，不降低验收，不把handoff记成恢复成功。
- 2CPU、节点1200秒、32命令；单命令600秒、evaluator/replay各900秒、cleanup120秒。零Provider Meter拒绝任何模型调用；无Fake模型、无工具/恢复模型请求、无新增Token/费用。协议冻结时设两小时工程运行上界，新项需余2100秒，保留120秒清理余量，不延长旧付费授权。
- 真正cleanup失败或意外模型请求全局停止，其他失败继续后续固定项目。继承#538独立分类适配器只区分源码拒绝与物理cleanup，strict不变；旧result不回写。
- 协议保存全部执行组件SHA及任务/归档。create-once输出保存原协议、源码hash、候选/生成收据、命令与完整日志、交接、验证/重放/交付与清理；seal后只读。

## 报告与决定

逐项报告generated / needs_agent / strict_completed / not_observed，生成耗时与总耗时、Shell、所有层验收和0模型用量。不得将未执行测试/交付/replay填通过或失败。独立stdlib审计复算inventory、固定任务/计划/验证/原源码/Session/实际容器不存在及零请求。

不预设效果门槛：至少一条真实严格闭合才能声称该路径工程可用；某构建系统失败则明确该系统尚未资格，允许提出下一新身份，不能本身份改生成器后补跑。若全部失败，则先定位模板覆盖/接口缺口。3/3也不是效果证明，后续仍需共享接口的公平比较。保持原研究主线、不加P2、不改RQ3分母、不发布总体成本优势。
