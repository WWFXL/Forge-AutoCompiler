# 契约驱动修复 mechanism v1 36-arm formal collection 执行身份

日期：2026-09-30
状态：formal_collection_authorized_not_started
Tracking Issue：#363

## 授权来源与父证据

研究负责人已明确授权在 availability 通过后执行冻结的 36-arm formal collection。唯一 DeepSeek
`deepseek-flash` availability 已绑定 `main@09d7ff36ca081f5bfa39f8e1d6f3b3daa53c93a0` 一次通过；create-once
marker SHA-256 为 `8527d64acc50a88ea0d5f8b64fc25971d68294fb142b043f1e889586ad088bee`，并由
PR #362 的版本化报告完成只读审计。本身份不重复 availability 请求。

## 样本、schedule 与条件

本身份原样继承父 candidate 的六项目、exact commit、12 个 matched checkpoints、36 个 arms、项目顺序、
checkpoint 顺序、arm 顺序和 opaque clone/evaluation identity。每个项目各有 `delivery_target` 与 `provenance`
checkpoint；每个 checkpoint 严格串行运行 C0/T1/T2 的冻结排列。

parent 使用冻结 reference recipe 建立有效产物和 functional oracle，再在生产 candidate submission 边界形成唯一
authoritative rejection：`delivery_target` 为 `target_mapping_invalid`；`provenance` 为 generalized P2 的
`build_system_unproven / opaque_wrapper`。checkpoint 在 rejection 返回后、任何 continuation model request 前冻结。

三臂共享 source、commit、rootfs、workspace、artifacts、parent command history、candidate request、rejection、
message prefix、remaining budget、tool policy 和 authority hashes。唯一允许差异为：C0 generic failure；T1 增加
classification 与 bounded finding；T2 再增加不含命令、argv、shell、patch 或答案的 abstract repair goal。

## Continuation 与严格终点

每个 arm 从同一 checkpoint 的独立 opaque clone 启动 Runtime v3 continuation。Provider、profile 与 actual model
固定为 DeepSeek `deepseek-flash`；non-streaming、无 fallback、`parallel_tool_calls=false`、SDK retry 为 0。
provenance 修复必须通过真实 `run_container_bash` tool surface 形成 direct CMake、Make 或 Autotools command
evidence；禁止直接写 command record。

二元终点 `strict_post_checkpoint_conversion` 只有在 candidate accepted、functional oracle、provenance、external
evaluator v3、clean replay、cleanup 与 0 managed orphan 全部通过时取 1。模型行为失败、预算耗尽、无 submit、
再次拒绝或 strict evaluation 未通过取 0。Provider endpoint failure 单独标记 censor，不填成 0。

## 预算、retry 与停止规则

- 每 arm 最多 8 个 Provider request attempts、8 turns、24 graph steps、24 tool calls、16 commands；
- continuation 600 秒、command 300 秒、evaluator 900 秒、clean replay 900 秒、cleanup reserve 120 秒；
- 单臂和总体 `max_recorded_tokens=null`，每次响应记录 input/output/total tokens，token 总量不是停止条件；
- 36 arms 最多 288 个正式 Provider request attempts；已完成 availability 的 1 attempt 不计入该上限；
- 每个 logical request 最多一次 transport retry，仅限 0 response、0 recorded token、0 tool side effect，且计入
  8-attempt arm 上限；模型行为失败不得 retry；
- 第一个 endpoint-censored arm 保留并继续 schedule；第二个出现后闭合当前 checkpoint cleanup 并停止 identity；
- identity、checkpoint、ledger、budget、model identity、evaluator、cleanup 或 orphan 异常立即停止；
- 禁止人工 retry、replacement、backfill、失败 arm 重跑、观察结果后重排或扩样。

## Evidence 与分析

正式 evidence 与 availability marker 共用冻结 create-once root，但 formal runner 只能新增预注册 batch、checkpoint、
arm、ledger、runtime-events、candidate 和 report 路径，不能改写 marker。runner 只接受完整连续 evidence 前缀；
已终结 arm 不重跑，缺 marker 的既有 evidence 不导入，partial/failed/censored observation 全部保留。

主要比较为 C0 vs T1，使用六个 project scores 的双侧 exact sign-flip test，并要求 `Delta_01 >= +1/3`；只有
统计与实际意义门禁都通过才检验 T1 vs T2，并要求 `Delta_12 >= +1/6`。C0 vs T2 只作支持性描述。相关 arm
不完整时对应 test 为 `null`，报告 observed-complete estimate 与 best/worst identification interval。

本研究仍是固定 36-arm、低功效的毕业论文机制研究。availability、基础设施测试和单个 arm 轨迹均不能解释为
treatment effect、统计显著性、总体成功率或模型排名。
