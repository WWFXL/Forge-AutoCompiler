# 简洁主构建与异常状态路由：实现结果及中断记录

2026-11-05，Issue #693；论文证据编号E49。本轮完成共同判定修复、最小语义路由实现与真实运行；**24槽比较在第3槽服务权限错误后停止，尚无Jev效果结论**。

## 本轮改变了什么

新任务版本`main-build-v1`只要求主要程序/库实际构建并得到有效产物。完整作者测试不再默认必需，正常完成时明确记`not_required`；不记为测试通过。主要产物检查、原源码/测试保持、精确交付、干净构建重放及清理分别保存。`main_build_task_completed`要求主要构建、原源码终态检查与清理通过；交付和重放另列，旧`full_completed`不用于新任务比较。旧实验的任务、失败和分母保持原样。

共同命令判定不再要求Shell文本必须被`infer_command_roles`识别为build。Workflow和强工具Agent都接受结构化build角色及其实际成功记录，再以独立主要产物检查确认结果。例如`CM=cmake; "$CM" --build build --parallel 2`可以正常执行；只声明build、退出0却没有有效产物仍不能通过。这解决的是动作表述误拦，不证明任意命令语义都能准确识别。

新增异常路由读取阶段目的、实际命令、退出/日志、配置观察及主要产物观察。规则和Jev共享候选：依据作者最低CMake版本升级工具、恢复已有配置后缀、补充未完成的产物观察；其余问题交Flash恢复Agent。Jev仅在异常/不确定且存在候选时调用，一次请求分别选择状态类别和已有动作，不能生成Shell或覆盖实际反证。正常路径零Jev请求；每槽最多两个不同局部动作。实现及工程检查详见[准备报告](2026-11-05-main-build-state-routing-preparation.md)。

## 工程验证与正式比较分开

45项相关检查、Ruff/格式检查通过。两条真实Docker工程路径均完成主构建、交付、干净重放、原源码保持和清理：

| 工程路径 | 实际观察 | 总秒数 | 模型请求 |
|---|---|---:|---:|
| jsoncpp变量命令 | 变量形式cmake构建不再被误拦 | 41.79 | 0 |
| double-conversion自然失败恢复 | 原CMake版本不足→一次规则升级工具→重新配置构建 | 212.10 | 0 |

两条路径仅支持实现可执行，不加入下面的24槽效果分母。工程原件为`/home/yiwei/.codex/outputs/forge-main-state-engineering-2026-11-05-v1`，`engineering-summary.json`保存结果和实际容器清理核验。

正式身份`cpp-build-main-state-routing-comparison-v1`固定E48六项目的首重复基础Forge初始方案，×两重复×规则/Jev，共24槽；经验关闭，恢复统一Flash low，任务/资源/候选/检查相同。项目为jsoncpp、double-conversion、libite、libogg、highwayhash、xxhash，均已开发暴露，非holdout。第二重复反转顺序，保留所有正常方案，没有制造故障。这是固定方案的路由组件比较，不是端到端规划系统比较。

## 实际结果：3槽终态、21槽未启动

| 槽 | 项目/方法 | 主构建/新任务 | 交付/干净重放 | 路由/恢复 | 总秒数 |
|---|---|---|---|---|---:|
| 1 | jsoncpp/规则 | 通过/通过 | 通过/通过 | 无异常，0请求 | 41.92 |
| 2 | jsoncpp/Jev | 通过/通过 | 通过/通过 | 无异常，0请求 | 41.83 |
| 3 | double-conversion/Jev | 未观察/未完成 | 未观察/未观察 | 首次Jev服务拒绝，未产生决策 | 5.00 |
| 4–24 | 原计划其余条件 | 未观察 | 未观察 | 未启动 | — |

前两槽作者测试为`not_required`、原源码检查和清理通过。第3槽已观察到配置失败，但尚未编译，因此主产物、作者测试、交付、重放和原源码终态检查均未观察；实际清理通过。不能把21个未启动槽填作方法失败，也不能以每组已观察数不同的部分数据比较成功率。整批采集89.52秒，三个槽均有终态、没有未闭合活动槽。

第3槽执行`cmake -S . -B build`，退出1；日志明确为“CMake 3.29 or higher is required. You are running version 3.28.3”。系统从作者声明产生`upgrade_cmake`候选，拟安装满足最低版本的工具并重做配置/构建。Jev收到该真实状态及候选后，SDK报`TypeSafePermissionDeniedError`，`usage_known=false`。这是Provider权限层阻塞，未得到语义选择，不能解释为Jev选择错误或不能修复。保存记录没有更细的服务拒绝说明，不能断定是密钥、账户还是模型权限的具体原因；本轮没有改密钥、换路由或再次请求。

原冻结`analysis.json`中的`triggered_slots=0`按已完成`decision_count`统计；首次请求失败发生在写decision之前。派生分析因此同时列明：**发起Jev请求的槽1个、成功响应0、完成决策0、局部动作0、Flash恢复请求0**，而非“没有触发Jev”。

## 费用、停止及证据

已知完成响应费用为0美元、已知响应Token为0，但有1次Jev请求用量未知，**本轮总模型费用和总Token未知，不能报告为零支出**。原汇总的`new_estimated_cost_usd=0.0`仅是已完成响应之和。Flash实际请求0；Jev输入0.042美元/百万Token的历史估价没有被用于把未知用量补零。

六份来源方案历史初始规划共14请求、0.0381387美元，非本轮新付费。若24槽全部执行，每组12次等额计入对应来源费为0.0762774美元；本轮未执行21槽，不把这一假设投入写成实际支出，也不以执行阶段零规划请求称端到端免费。

用户“开始执行！”覆盖前述四步24次计划；助手自行收紧新增2美元和UTC05:38:28–09:38:28（北京时间13:38:28–17:38:28），准备计入，不冒称数字是用户逐项提供。本次按未知用量规则停止，未自动重试、补槽、扩批或换Provider。服务恢复前不启动下一付费比较。

- 运行提交：`d2be5ce0224cc20a22a0a3c1d6338aa5889e6160`；[manifest](../../benchmarks/manifests/cpp-build-main-state-routing-comparison-v1.json) SHA-256：`134de492c364ca554257de246b12d86c4f15f3109699ddc6760a844449b70a39`；[协议](../../benchmarks/preregistrations/cpp-build-main-state-routing-comparison-v1.md)。
- 冻结原件：`/home/yiwei/.codex/outputs/forge-main-build-state-routing-v1`；inventory：`5d8a5178de26e035c29d6b6534835b9f6ae7f50ca39d79dde4c87ff738b790f2`，2544普通文件/8符号链接/73045924字节。封存后一次只读核验通过，未改原件。
- [派生汇总](../../benchmarks/analyses/main-build-state-routing-2026-11-05/summary.json)、[24槽状态CSV](../../benchmarks/analyses/main-build-state-routing-2026-11-05/slots.csv)、[失败请求指针与状态包](../../benchmarks/analyses/main-build-state-routing-2026-11-05/provider-blocker.json)、[只读核验](../../benchmarks/analyses/main-build-state-routing-2026-11-05/verification.json)。CSV空值表示未观察，不转填false。
- 三槽共5个实际容器的10个名称/ID引用已核验不存在。授权、运行日志、发布收据在`/home/yiwei/.codex/outputs/forge-main-state-session-2026-11-05-v1`。

## 论文可用内容与下一步

本轮可用于第3章简洁任务定义、第4章事实观察与受限语义路由实现，以及第6章中断/可用性限制。工程路径支持修复和状态到动作链可执行；两个正常槽只说明相同方案在新范围下实际构建和重放成功。**不支持Jev相对规则的效果、成本收益、广泛语义准确率或新的系统排名。**

下一步先解决Jev当前访问权限及该次用量问题，再以新身份明确剩余比较或完整新比较范围；不续写本身份、不把权限修复当科研增益。若服务短期不可用，可优先整理已有完整系统/状态/经验实验的论文内容，是否保留Jev为待验证扩展由实际可用性与后续证据决定，无需因此更换研究主线。
