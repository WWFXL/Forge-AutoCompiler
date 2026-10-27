# 共同候选接收修复与配置状态组件消融准备

本阶段为工程修复和实验准备，直接解除上一轮五项未完成中可定位的接口问题。已完成三份原JSON候选的实际Agent接收回放、原说明文字拒绝、错误路径反馈后的继续调用，以及一次tinyxml2完整构建/原测试/交付/干净重放。真实Provider调用和新增模型费用均为0；这些结果不回填旧24槽，不当作新模型效果。

## 已修复的两处问题

第一处是候选呈现。新`propose_received`同时接收原结构化工具调用、完整JSON对象、仅带可选ObservedBuildActions标题的单个JSON围栏，全部复用原ObservedBuildActions与assemble_observed。自由说明、多个对象/围栏、重复字段和非标准JSON不猜测。原始响应在解析前保留，成功收据记录presentation；原schema/装配的一次纠错、无执行变化拒绝、探索额度、截断/模型身份检查与全部用量计量仍保持。被拒候选的后续反馈也直接绑定本槽原响应与SHA，支持工具和文本两种来源，不伪造tool_call。

第二处是字面引用反馈。模型把`~6~.mk`作为read_source路径时，工具应拒绝该读取，但后续材料不应再因错误参数内的标记终止。新共同接口在原包包含字面`~数字~`时保留完整原文，只使用既有完整字符串共享，不做子串因子编码。原参数、拒绝原因和完整上一工具轮次仍发送；不自动把引用展开成正确文件。原共享保留字段/哈希/还原及消息大小检查仍保持；若材料更长，原门槛继续生效。

新接口仅在独立入口上下文生效；上一轮328个冻结组件的映射和实际SHA均保持。没有修改原任务源码或原测试，没有调整固定验收。

## 原始案例回放

输入来自`forge-goal-state-paired-flash-v1`原只读响应。脚本模型逐字重放content，使用明确的scripted-common身份及零用量，不调用Provider。

| 原槽 | 项目 | 新接收链观察 | 是否执行构建 |
|---:|---|---|---|
| 7 | yaml-cpp | 原样完整JSON通过同一结构与装配 | 否 |
| 11 | tinyxml2 | 原样完整JSON通过同一结构与装配 | 是，另立脚本回放 |
| 14 | check | 原说明文字仍被拒绝，未额外请求 | 否 |
| 18 | snappy | 原schema标题＋单JSON围栏通过同一结构与装配 | 否 |

tinyxml2使用原槽11候选的原样content，经新共同入口执行：原源码/链接保持，构建、原测试、精确静态库交付、同镜像完整clean replay、cleanup均通过，Session completed；1次脚本模型响应、0 recorded Token、0真实Provider、0新增费用。构建及重放两个容器已实际inspect确认不存在。这证明这一份原候选此前受到接收接口阻断，不能推广成三个候选都能构建成功或整体成功率提升。

非法共享引用回归实际走read_source错误→下一请求保留原错误及参数→脚本Agent改读真实文件→提交候选；没有隐式路径修复。53项必要局部及相邻回归通过，Ruff check/format及候选CLI检查通过；没有重复全量产品测试或完整参考构建。

回放记录位于`/home/yiwei/.codex/outputs/forge-common-harness-session-2026-10-28/original-case-replay-v1/`，summary.json、逐案例收据、tinyxml2-complete-result.json、完整Session与resource-check.json保留。执行脚本同会话replay_original_cases.py，测试日志final-targeted-tests.log；版本化派生摘要见`benchmarks/analyses/cpp-build-common-harness-repair-v1.json`。旧24槽19完整/5未完成以及原RQ3分母均不变。

## 下一项可执行真实比较

[Issue635](https://github.com/WWFXL/Forge-AutoCompiler/issues/635)跟踪`cpp-build-goal-state-component-ablation-flash-v1`：simdutf/snappy/yaml-cpp三个已见CMake任务×两重复×三臂，共18槽。

| 实验臂 | 共同候选/反馈修复 | 持续目标呈现 | 实际配置核对与有界选择 |
|---|---|---|---|
| common_model_workflow | 启用 | 不额外提供 | 关闭 |
| goals_only_model_workflow | 启用 | 启用 | 关闭 |
| goals_state_model_workflow | 启用 | 启用 | 启用 |

前两臂比较目标呈现增量，后两臂比较实际配置观察/选择的增量。两目标臂使用相同目标清单和提示；全部共用Flash low、原任务、资源与完整验收。各臂独立初始模型方案，不能称固定同一方案的纯动作反事实。若再次没有自然配置偏离或直接动作，照实报告未触发，不制造错误替代自然比较。更大系统比较及CXXCrafter安排在组件边界清楚后。

候选manifest SHA256为`87fd9cf72bef05c23dd9d38f6a92a895079731c8a03abc1b5f915beaaf205ca1`，保留原328组件并新增4个运行/协议组件。入口`scripts/forge_build_goal_state_ablation.py`提供prepare、check-prepared、analyze及原授权运行接口。原最后配置后的观测、最多一次有证据的BOOL修订和复杂情况交Agent保持；HAVE_*探测不能强设。

本18槽尚未创建正式attempt、读取凭据或调用模型。设计费用上限10美元、建议新4小时窗口，准备计入；原窗口已于UTC2026-10-27 17:49:38过期，需新有效授权绑定候选及release。沿用node1200/replay1200/cleanup余量300、新槽2700、请求准入600秒，SDK自动重试0；未知用量、身份异常或cleanup失败即停、不补槽。原失败与未观察保留，不改变科学主张或研究主线。

```bash
cd backend
PYTHONPATH=. uv run python ../scripts/forge_build_goal_state_ablation.py --check-prepared
```

正式运行在新授权后使用同一入口及`--candidate`、`--authorization-root`、`--output-root`，无需再次进行参考资格链。发布以本阶段结果PR的实际HEAD CI及科研分支合并状态为准，不进入main。
