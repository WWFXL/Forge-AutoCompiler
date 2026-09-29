# 契约驱动修复三臂候选预注册决策包

日期：2026-09-29
状态：研究负责人已冻结候选设计，未授权 candidate identity 已生成并待审阅
工作类型：结果分析与实验设计（0 Provider、0 credential read、0 formal attempt、0 formal evidence write）
Tracking Issue：#353

## 1. 本轮决策问题

Issue #352 已证明 Runtime v3 能从 delivery/target 与 provenance 两类 authoritative rejection 创建
state-matched C0/T1/T2，并以确定性 continuation 闭合 candidate、functional oracle、provenance、external
evaluator、clean replay 和 cleanup。该 qualification 不产生 treatment outcome。

现在需要决定：毕业论文机制实验采用可执行的 36-arm 固定样本研究，还是扩大到能够在额外假设下获得常规
统计功效的规模；随后才能冻结具体任务、分析、Provider、预算和停止规则。

## 2. 可辨识性审计

当前候选为 6 个项目，每项目一个 delivery/target checkpoint 和一个 provenance checkpoint，每个 checkpoint
运行 C0/T1/T2，共 12 个 matched checkpoints、36 arms。以 C0 vs T1 的二元严格转换为例，效应只给出绝对
风险差仍不足以唯一确定功效；paired test 还取决于有利与有害 discordance 的比例。

对 12 个 checkpoint 的双侧 exact paired test 做结果盲枚举，得到：

| 真实绝对效应 | discordance | 估计功效 |
| ---: | ---: | ---: |
| `+1/6` | `1/6`--`1` | `0.008`--`0.071` |
| `+1/3` | `1/3`--`1` | `0.164`--`0.196` |
| `+1/2` | `1/2`--`1` | `0.391`--`0.613` |

上述数字由 `scripts/forge_contract_repair_design_sensitivity.py validate` 复算；脚本只枚举联合 discordance
分布，不读取仓库内任何新实验 outcome。

在真实效应 `+1/3` 时，达到约 80% 功效所需 checkpoint 数随 discordance 假设变化：无有害 discordance
约需 23 个，中等 discordance 约需 36 个，高 discordance 约需 56 个，对应 69、108、168 arms。正式分析
还应以 6 个 project block 为聚类单位，因此 12-checkpoint 计算已经是偏乐观的可辨识性说明。

结论：36 arms 可以形成范围可控的毕业论文机制研究，但不能预先称为“功效充分的确认性总体效应实验”。
推荐把它定位为固定样本、预注册、可证伪的机制研究，以效应量、方向一致性和 exact test 为主；若目标改为
常规 80% 功效，应先扩大到至少 36 个 checkpoint，并重新核算项目数、成本和毕业时间。

## 3. 推荐的最小有意义效应

推荐把 C0 vs T1 的最小有意义效应冻结为：

```text
Delta_01 = mean_checkpoint(Y_T1 - Y_C0) >= +1/3
```

在 12 个 checkpoint 上，这等价于 T1 相对 C0 至少净增加 4 次严格转换。该门槛与 behavioral v2 和
multi-checkpoint v3 观察到的 `+2/6` 量级一致，但选择依据是毕业论文的实际意义：低于 4 次净转换时，新增
checkpoint、反馈投影和验证复杂度难以形成有说服力的方法收益。历史 pilot 只提供量级参照，不作为新研究
的先验成功证据。

对 T1 vs T2，推荐把 `+1/6` 作为次级实际意义门槛，即抽象 repair goal 至少净增加 2 次严格转换。该比较
只有在主要比较通过预注册 gate 后才进入正式检验；否则只报告描述性结果。

## 4. 结果盲样本规则

样本只使用已冻结的 `stage-c-source-pool.json` 与零 Provider `stage-c-task-qualification-result.json` 中的 source、
exact commit、构建系统、任务合同和 oracle，不按 Stage C 或历史机制 outcome 选项目。

为避免直接复用 Stage C v8 Runtime v3 remediation canary 的四个项目，先排除 `theora`、`json-c`、
`libjpeg-turbo` 和 `oatpp`。随后在预先存在的 source-pool 顺序中，对 CMake、Make、Autotools 各取第一个
small 和第一个 medium 项目。冻结候选为：

| 项目 | exact commit | 构建系统 | 规模 | 任务合同 |
| --- | --- | --- | --- | --- |
| `leveldb` | `7ee830d02b623e8ffe0b95d59a74db1e58da04c5` | CMake | medium | `leveldb-static-library` |
| `libsoundio` | `49a1f78b50eb0f5a49d096786a95a93874a2592a` | CMake | small | `libsoundio-static-library` |
| `8cc` | `b480958396f159d3794f0d4883172b21438a8597` | Make | small | `8cc-executable` |
| `lz4` | `0774d05537f9762f838f7ab541b7765f1a729cb5` | Make | medium | `lz4-library-and-cli` |
| `rnnoise-0.1.1` | `6cbfd53eb348a8d394e0757b4025c6ded34eb2b6` | Autotools | small | `rnnoise-static-library` |
| `libsndfile` | `b9103bd48b6c8fb517ae737fe3baee0c718b804c` | Autotools | medium | `libsndfile-static-library` |

这六个项目有历史完整系统模型运行，但选择规则不读取那些 outcome，且本研究使用新的 parent、candidate
submission checkpoint、feedback contract 和 experiment identity。允许的外推范围只包含这六个固定的
small/medium C/C++ 项目，不能扩展为所有仓库或 large 项目。

## 5. 十二个 checkpoint

每个项目建立两个独立 parent checkpoint：

1. `delivery_target`：目标产物和 functional oracle 已成立，candidate 只因生产 CandidateVerifier 的唯一
   `target_mapping_invalid` finding 被拒绝；修复需要提交与人工冻结 target contract 一致的映射。
2. `provenance`：目标产物和 functional oracle 已成立，candidate 先经过生产 verifier，再只因 P2 的
   `build_system_unproven / opaque_wrapper` 被拒绝；修复必须通过真实 compiler tool surface 建立 direct
   CMake、Make 或 Autotools provenance，不得直接写 command record。

checkpoint 在 rejection 返回后、任何下一次模型请求前冻结。每个 checkpoint 的三臂共享 source、rootfs、
workspace、artifacts、command history、candidate request、rejection、message prefix、remaining budget、
tool policy 和 authority hashes；只允许 Issue #352 已验证的 feedback projection 不同。

## 6. Schedule 与随机化

- 项目顺序由新 identity 的固定 seed、repository URL 和 exact commit 计算 SHA-256 后排序。
- 每个 stratum 各使用一次 C0/T1/T2 的六种排列，使每个条件在第一、第二、第三位置各出现两次。
- 三个条件随机映射到 opaque clone identity；external evaluator、oracle、replay 和 cleanup 不接收 arm label。
- 六个项目中三个先运行 delivery/target，三个先运行 provenance，按冻结 hash 交替分配。
- 所有 Provider 请求串行执行，`parallel_tool_calls=false`；禁止观察 outcome 后重排、replacement、backfill 或
  schedule extension。

## 7. 终点与分析

arm 的主要终点为二元 `strict_post_checkpoint_conversion`，必须同时满足 candidate、functional oracle、
provenance、external evaluator、clean replay 和 cleanup。模型行为失败、预算耗尽、无 submit 或再次拒绝均为
`0`；合法 endpoint censoring 单独记录，不改写为模型失败。

对每个 checkpoint 和项目定义：

```text
delta_01_checkpoint = Y_T1 - Y_C0
delta_12_checkpoint = Y_T2 - Y_T1
project_score       = mean(delivery_target_delta, provenance_delta)
Delta               = mean(six project_scores)
```

主要比较 C0 vs T1 使用 6 个 project scores 的双侧 exact sign-flip test，`alpha=0.05`。由于样本离散，只有
方向高度一致时才可能拒绝零假设；无论 p 值如何，都报告 12 个 matched outcomes、discordance table、
`Delta_01`、每个 stratum 的描述性差值和完整删失情况。

多重比较采用固定顺序 gatekeeping：

1. C0 vs T1 先检验，且必须同时满足 `Delta_01 >= +1/3` 才支持“固定样本中存在实际有意义增益”；
2. 只有第 1 步通过，T1 vs T2 才以 `alpha=0.05` 检验，并以 `Delta_12 >= +1/6` 判断实际意义；
3. C0 vs T2 只作支持性效应量与分层描述，不产生第三个确认性 p 值。

若效应达到门槛但 exact test 未通过，结论为“观察到实际量级、统计上不确定”；若未达到门槛，不能用显著性
或个别项目轨迹声称机制有效。两个 stratum 各只有 6 个 checkpoint，只作预注册的描述性异质性分析。

每项比较还必须满足预先冻结的完整性条件：

- C0 vs T1 的主要检验要求 12 个 checkpoint 的 C0 和 T1 全部 eligible；任一相关 arm 被 endpoint 或
  infrastructure censor 后，`primary_test=null`；
- T1 vs T2 要求 12 个 checkpoint 的 T1 和 T2 全部 eligible；缺失时 `secondary_test=null`，不影响已经完整
  的 C0 vs T1 主要比较；
- 被删失或停止后未运行的 arm 不填成 `0`，也不从 schedule 分母中消失；报告 observed-complete estimate，
  并把缺失 arm 分别按最不利和最有利结果计算 `Delta` 的识别区间；
- 只有模型行为失败、合法预算耗尽、无 submit 或再次拒绝记为真实 `0` outcome。

## 8. Provider、预算与删失候选

为保持与当前服务器模型配置一致，候选 Provider 冻结为 DeepSeek `deepseek-flash`，固定 endpoint、
非 streaming、无 fallback、300 秒 request timeout。该选择只用于控制实验身份，不支持模型排名。

每 arm 推荐上限：

- 8 个 model request attempts（transport retry 也计数）、8 turns、24 graph steps；
- 不设置 recorded-token ceiling；
- 24 tool calls、16 commands；
- continuation 600 秒、单命令 300 秒、evaluator 900 秒、clean replay 900 秒、cleanup reserve 120 秒。

36 个正式 arms 的机械上限为 288 request attempts。formal marker 前的一个 availability logical request 最多
有一次严格限定的 transport retry，因此包含 availability 的 identity 机械上限为 290 Provider request
attempts。每次响应必须记录 input/output/total tokens，但单臂和总体 token 总量都不作为终止条件；request、
turn、graph step、tool、command、墙钟和 cleanup 预算仍提供有限执行边界。本候选不引入货币停止条件，且不
授权任何费用或 Provider 调用。

删失与停止规则候选：

1. formal marker 前只允许一次固定响应的 availability qualification；失败则不创建 batch；
2. 每个逻辑请求最多一次 transport retry，且仅限 0 响应、0 recorded token、0 工具副作用；retry 占用 arm
   的 8-request 上限，模型行为失败不得 retry；
3. 第一个 endpoint-censored arm 保留并继续冻结 schedule；出现第二个 endpoint-censored arm 时，在当前
   checkpoint cleanup 后停止整个 identity；
4. identity、checkpoint、ledger、budget、evaluator、cleanup 或 orphan 异常立即停止；
5. 禁止 replacement、backfill、失败 arm 重跑和观察结果后的追加样本。

## 9. 已冻结决策与后续边界

研究负责人已于 2026-09-29 接受 36-arm 固定样本机制研究，冻结 `+1/3` 主要最小有意义效应，并采用上述
六项目、双 stratum、project-level exact analysis 和 fixed-sequence gatekeeping。该定位明确接受低功效与
固定样本外推边界。

同时冻结：

1. Provider profile 与实际模型名称均为 DeepSeek `deepseek-flash`；
2. `max_recorded_tokens=null`、`total_max_recorded_tokens=null`，逐响应计量 tokens，但 token 总量不作终止条件；
3. 每 arm 8 个 request attempts，36 个正式 arms 最多 288 个 request attempts，另有 availability 最多 2 个 attempts；
4. 一次严格限定的 transport retry，以及第二个 endpoint-censored arm 后停止；
5. 禁止 replacement、backfill、失败 arm 重跑和观察结果后扩样。

独立 candidate manifest、const Schema、preregistration 和 plan-only runner 已生成。candidate 通过代码审查
仍不等于执行授权；credential、Provider、formal attempt、formal evidence 和 release revision 必须由后续
create-once authorized identity 单独开启或冻结。
