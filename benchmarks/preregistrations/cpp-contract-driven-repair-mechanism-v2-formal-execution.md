# 契约驱动修复 mechanism v2 独立 36-arm formal collection 执行身份

日期：2026-09-30
状态：formal_collection_authorized_not_started
Tracking Issue：#377

## 授权与父证据

研究负责人已明确授权派生、测试、提交、推送并合并本独立 formal collection identity，并在合并后的干净
`main` 上通过严格 preflight 后执行唯一 36-arm batch。该授权同时覆盖 `DEEPSEEK_API_KEY` presence 检查、
DeepSeek `deepseek-flash` Provider 调用、必要 Docker formal Session、formal attempts 和 create-once evidence。

父 availability execution identity 由 PR #372 合并为
`main@12681ffb0fd2997e2f572f3355e02b50a1b79744`。唯一 availability request 首次通过；marker SHA-256 为
`73a505f396278eaa93430264fb3ef8d86964891763d242d419e4793b475f21ee`，由 PR #374 合并的 JSON/Markdown
报告完成只读审计。本 identity 只读取并核验该 marker，禁止重复 availability request。

## 独立性、样本与 schedule

本 identity 原样继承 mechanism v2 candidate 的六项目、exact commit、12 个 matched checkpoints、36 个 arms、
项目顺序、checkpoint 顺序、condition 顺序、预算、停止规则、opaque clone IDs 和 opaque evaluation IDs。
每项目各有一个 `delivery_target` 和一个 `provenance` checkpoint；每个 checkpoint 严格串行运行冻结的
C0/T1/T2 排列。

本 identity 使用 `.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent`。开始前
该 root 必须只有已冻结 availability marker，不能含 batch、checkpoint、arm 或其他文件。v1 evidence inventory
必须保持 `9 files / 66,466 bytes / 24019a372a3b49fe6dcf1ed16521341f3c6d2fb5`，且不导入任何 v1 marker、
checkpoint、ledger、result、token 或 outcome；v1 sequence 1 T2 observation 永久排除于 v2 分析。

## Checkpoint、反馈与终点

parent 使用冻结 reference recipe 建立有效产物和 functional oracle，再在生产 candidate submission 边界形成
authoritative rejection：`delivery_target` 使用 `target_mapping_invalid`，`provenance` 使用 generalized P2 的
`build_system_unproven / opaque_wrapper`。checkpoint 在 rejection 返回后、任何 continuation model request 前
原子冻结。

三臂共享 source、commit、rootfs、workspace、artifacts、parent command history、candidate request、rejection、
message prefix、remaining budget、tool policy 和 authority hashes。唯一允许差异为：C0 generic failure；T1 增加
classification 与 bounded finding；T2 再增加不含命令、argv、shell、patch 或答案的 abstract repair goal。

每个 arm 从同一 checkpoint 的独立 opaque clone 启动 Runtime v3 continuation。Provider、profile 与 actual model
固定为 DeepSeek `deepseek-flash`；non-streaming、无 fallback、`parallel_tool_calls=false`、SDK retry 为 0。
provenance 修复必须通过真实 compiler tool surface 形成 direct CMake、Make 或 Autotools evidence，禁止直接写
command record。

二元终点 `strict_post_checkpoint_conversion` 只有在 candidate accepted、functional oracle、provenance、external
evaluator v3、clean replay、cleanup 与 0 managed orphan 全部通过时取 1。模型行为失败、预算耗尽、无 submit、
再次拒绝或 strict evaluation 未通过取 0；合法 endpoint failure 单独标记 censor。

## 预算、retry 与停止规则

- 每 arm 最多 8 个 Provider request attempts、8 turns、24 graph steps、24 tool calls、16 commands；
- continuation 600 秒、command 300 秒、evaluator 900 秒、clean replay 900 秒、cleanup reserve 120 秒；
- 单臂和总体 `max_recorded_tokens=null`；逐响应记录 input/output/total tokens，token 总量不是停止条件；
- 36 arms 最多 288 个 formal physical request attempts，availability attempt 不计入该上限；
- 每个 logical request 最多一次 transport retry，仅限 0 response、0 recorded token、0 tool side effect，并计入
  单 arm 8-attempt 上限；模型行为失败或不满意答案不得 retry；
- 第一个 endpoint-censored arm 保留并继续 schedule；第二个出现后完成当前 checkpoint cleanup 并停止 identity；
- identity、checkpoint、ledger、budget、model、image、evaluator、cleanup、evidence 或 orphan 漂移立即停止；
- 禁止人工 retry、availability 重跑、replacement、backfill、失败 arm 重跑、重排或 schedule extension。

## Evidence、封口与分析

formal runner 临时把 frozen v1 execution engine 绑定到本 v2 protocol，并安装已审阅的 marker repair；binding 只允许
串行进入且退出后恢复。attempt、batch progress、正常 batch 终态和异常 batch 终态均通过 repair 原子封口。原始
evidence 只在 manifest 授权路径 create-once 写入，不覆盖 availability marker；runner 只接受冻结 schedule 的连续
前缀，已终结 batch 禁止重跑。

主要比较为 C0 vs T1，使用六个 project scores 的双侧 exact sign-flip test，并要求 `Delta_01 >= +1/3`；只有
统计和实际意义门禁都通过才检验 T1 vs T2，并要求 `Delta_12 >= +1/6`。C0 vs T2 只作支持性描述。相关 arm
不完整时 test 为 `null`，同时报告 observed-complete estimate 和 best/worst identification interval。两个 failure
strata 分别报告。

本研究是固定 36-arm、低功效的毕业论文机制研究。Availability、qualification、基础设施测试、单个 arm 或不完整
batch 均不能解释为 treatment effect、统计显著性、总体成功率、Provider 可靠性或模型排名。只有完整 formal 数据
才能按上述预注册规则进行比较；即使完整，也只解释冻结的六项目样本与当前环境。
