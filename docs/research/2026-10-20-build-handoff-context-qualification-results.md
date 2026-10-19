# 接管上下文材料工程资格结果

Issue #511。#504 libverto-r2-plan固定测试失败后，已发出5次真实恢复请求但未交付修订；准备第10次总请求时50k门禁停止。此前误写“恢复前停止”的交接已按events.jsonl和request-5至9更正；原费用、strict及raw不变。本阶段0Provider、0凭据、0Docker，仅修复材料准入阻塞，不执行构建。

## 修复与资格

新增HandoffContextMeter复用原ContextCanaryMeter的费用、请求、工具schema、消息与结构化输出门禁。仅移除state.handoff.recent_commands中重复output_tail，记录其UTF-8字节数/SHA收据；顶层handoff原近期三条预览保持。全部命令身份/退出码/日志路径与原日志SHA、完成步骤、预算、完整任务/测试/方案不变。两份handoff身份错配则拒绝，核心仍超限也不调用模型。

v1按首次handoff材料重建，但新meter未还原此前读取索引/最近工具反馈，原/投影均准入（46410/32467字节），expected_observation=false。失败身份永久保留，不将其当修复成功。raw `/home/yiwei/.codex/outputs/forge-handoff-context-qualification-v1/`，81文件/1824746 bytes，inventory `1432f4cb545b272647d15363e2f8553d307c6a3891d66b0ec3d7836701c13ef3`。

v2独立冻结后，从原request-9.json恢复任务/方案/权威状态/接管及读取索引，应用最后三个tool.completed原文恢复工作集；真实LangGraph输入含原第九次AI工具调用及对应ToolMessage，系统提示词也取原请求原文。使用冻结remaining_seconds与新meter时间预算，因此是材料重建，不是原被拒请求的逐字节副本。

| 路径 | 实际观察 | 脚本请求/Token |
| --- | --- | ---: |
| 原ContextCanaryMeter | 50k门禁拒绝；即使去掉所有可淘汰源码片段，独立核验消息仍至少50916字节 | 0/0 |
| 新HandoffContextMeter | 原门禁下消息48515字节、工具schema2032字节；返回revision2候选，但不应用、不构建 | 1/0 |

v2 expected_observation=true，0未知usage，父封存与全部组件不变。raw `/home/yiwei/.codex/outputs/forge-handoff-context-qualification-v2/`，78文件/1771473 bytes，inventory `df52d2de72a886280bf298340736521194c707520794e29b36b285025139eb1f`。独立stdlib审计`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/handoff-context-v2-audit.json` valid=true、issues=[]，逐文件核验本阶段/父inventory、组件、原包/核心投影、读取索引、原拒绝下界与零Token脚本响应，不使用生产投影函数复算。

## 验证与边界

9项针对性及5项上下文相邻测试全部通过，Ruff/format通过。包含非破坏性投影、所有handoff身份字段错配拒绝，以及核心超限仍0请求；最终结果head须三项实际CI全SUCCESS后合并。

该修复只对新实验身份通过新增meter接线；#504/#506旧runner与冻结组件不改，不能回填旧失败或声称所有现有产品路径已自动采用。脚本模型只是复述原方案，未证明真实模型能修复0/6功能测试、提高自然恢复率、节省成本或状态选择器增量。消息余量仅1485字节，后续额外核心状态仍可能触发fail closed；不为成功提高50k上限。UTC22:00后本轮不再启动原3600秒保留的付费新请求/新臂，后续真实资格留给新授权窗口。
