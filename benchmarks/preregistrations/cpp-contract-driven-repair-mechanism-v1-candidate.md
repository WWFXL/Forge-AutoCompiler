# 契约驱动修复 mechanism v1 未授权候选预注册

日期：2026-09-29
状态：candidate_not_authorized
Tracking Issue：#353

## 研究定位

本候选预注册一项固定样本、可证伪的毕业论文机制研究：在相同 candidate submission rejection checkpoint、
模型、工具与有限运行预算下，比较普通失败载荷 C0、合同 finding T1，以及 finding 加抽象 repair goal 的
T2 对严格候选转换的影响。manifest 使用条件名 `c0/t1/t2`。

它不是功效充分的总体确认性实验。12 个 matched checkpoints 在真实绝对效应 `+1/3` 时，结果盲敏感性分析
估计功效约为 `0.16--0.20`；结论只适用于六个冻结的 small/medium C/C++ 项目和本协议条件。

## 样本与 checkpoint

样本从冻结 `stage-c-source-pool.json` 和零 Provider `stage-c-task-qualification-result.json` 选择。先排除已直接
进入 Stage C v8 Runtime v3 remediation canary 的 `theora`、`json-c`、`libjpeg-turbo`、`oatpp`，再按原
source-pool 顺序，对 CMake、Make、Autotools 各取第一个 small 和第一个 medium 项目：

| 项目 | exact commit | build system | size | target |
| --- | --- | --- | --- | --- |
| `leveldb` | `7ee830d02b623e8ffe0b95d59a74db1e58da04c5` | CMake | medium | `leveldb-static-library` |
| `libsoundio` | `49a1f78b50eb0f5a49d096786a95a93874a2592a` | CMake | small | `libsoundio-static-library` |
| `8cc` | `b480958396f159d3794f0d4883172b21438a8597` | Make | small | `8cc-executable` |
| `lz4` | `0774d05537f9762f838f7ab541b7765f1a729cb5` | Make | medium | `lz4-library-and-cli` |
| `rnnoise-0.1.1` | `6cbfd53eb348a8d394e0757b4025c6ded34eb2b6` | Autotools | small | `rnnoise-static-library` |
| `libsndfile` | `b9103bd48b6c8fb517ae737fe3baee0c718b804c` | Autotools | medium | `libsndfile-static-library` |

每个项目建立两个独立 parent checkpoint：

1. `delivery_target`：产物和 functional oracle 已成立，生产 CandidateVerifier 只产生
   `target_mapping_invalid`；
2. `provenance`：产物和 functional oracle 已成立，生产 verifier 后的 P2 criterion 只产生
   `build_system_unproven / opaque_wrapper`。

checkpoint 在 authoritative rejection 返回后、任何 continuation 模型请求前冻结。每个 checkpoint 的三臂
共享 source、commit、rootfs、workspace、artifacts、parent command history、candidate request、rejection、
message prefix、remaining budget、tools 和 authority hashes，只允许 feedback projection 不同。provenance
修复必须通过真实 compiler tool surface，禁止直接写 command record。

## 条件与盲化

- C0：只暴露普通 `verification_failed`；
- T1：增加 stratum 与 `code/paths/expected/actual` finding；
- T2：在 T1 上增加不含命令、argv、patch 或答案的抽象 repair goal。

项目顺序由固定 seed、repository URL 和 exact commit 的 SHA-256 排序。每个 stratum 分别把 C0/T1/T2 的
六种排列各使用一次；六个项目中三个先运行 delivery/target，三个先运行 provenance。三臂映射到唯一 opaque
clone identity；external evaluator v3 只接收 opaque evaluation identity、checkpoint 和 task identity，不接收
arm label、feedback projection 或 clone mapping。所有 arms 严格串行，`parallel_tool_calls=false`。

## 终点与分析

主要终点 `strict_post_checkpoint_conversion` 必须同时满足 candidate accepted、functional oracle、provenance、
external evaluator v3、clean replay、cleanup 和 0 managed orphan。模型行为失败、合法预算耗尽、无 submit 或
再次拒绝记为 `0`；endpoint/infrastructure censoring 单独记录，不填成 `0`。

主要比较 C0 vs T1 使用六个 project scores 的双侧 exact sign-flip test，`alpha=0.05`，并要求十二个 checkpoint
的等权差 `Delta_01 >= +1/3`。只有统计和实际意义条件同时通过，才检验 T1 vs T2；其实际意义门槛为
`Delta_12 >= +1/6`。C0 vs T2 只报告支持性效应量与分层描述，不产生第三个确认性 p 值。

主要比较要求所有 C0/T1 arms eligible；次级比较要求所有 T1/T2 arms eligible。缺失时相应检验为 `null`，
同时报告 observed-complete estimate，以及缺失 arms 在最不利和最有利结果下的识别区间。两个 strata 各只有
六个 checkpoints，只作预注册的描述性异质性分析。

## Provider、预算与停止规则

候选 Provider profile 与实际模型均为 DeepSeek `deepseek-flash`，固定 endpoint、非 streaming、无 fallback、
300 秒 request timeout，模型客户端 `max_retries=0`。每 arm 最多 8 个 model request attempts、8 turns、
24 graph steps、24 tool calls、16 commands；continuation 600 秒、命令 300 秒、evaluator 900 秒、clean replay
900 秒、cleanup reserve 120 秒。36 个正式 arms 最多 288 个 request attempts。

单臂和总体 `max_recorded_tokens=null`。每次响应仍记录 input、output 和 total tokens，但 token 总量不作为终止
条件。本候选不引入货币停止条件，也不授权费用、credential 或 Provider 调用。

formal marker 前只允许一个不含实验内容的 logical availability request：`Reply exactly with FORGE_READY.`，
唯一接受响应为 `FORGE_READY`；失败不创建 batch。它与正式请求一样，每个 logical request 最多一次
transport retry，且仅限 0 response、0 recorded token、0 tool side effect。availability 最多 2 个 attempts，
不计入 formal arm 的 288-attempt 上限，因此包含 availability 的 identity 机械上限为 290。正式 arm 的 retry
计入该 arm 的 8-attempt 上限。第二个
endpoint-censored arm 出现后，在当前 checkpoint cleanup 后停止整个 identity。identity、checkpoint、ledger、
budget、evaluator、cleanup 或 orphan 异常立即停止。禁止 replacement、backfill、失败 arm 重跑、观察结果后
重排或扩样。

## 授权与解释边界

本 candidate 的 credential、Provider、model creation、reachability、Docker、formal attempt、formal evidence 和
model token 授权均为 false；release revision 也尚未冻结。runner 只允许 `validate`、`plan`、
`show-checkpoint`，`reachability`、`run`、`batch` 必须在读取 credential、创建模型、运行 Docker 或写 evidence
前 fail closed。

Runtime v3 六臂 qualification 只证明双 stratum 的 state-matched continuation、严格终点与 cleanup 工程链路
可执行，不能解释为 treatment effect、统计显著性、模型排名或自然失败外推。candidate 通过测试和代码审查也
不构成正式实验授权；正式采集必须从合并后的 release revision 派生独立 create-once authorized identity。
