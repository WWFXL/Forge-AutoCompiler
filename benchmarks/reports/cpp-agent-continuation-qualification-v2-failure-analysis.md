# 固定 Agent continuation 资格 v2 失败机制分析

本文是对冻结 evidence 的只读 post-hoc 分析。它不修改 Q2 的正式分类、分母、门槛或停止决定，也不授权 retry、replacement、backfill、续跑或 controller 实现。

## 正式结果

- 27/27 arms 均形成分类终态并完成 cleanup；
- strict success：`12/27`；
- evaluated failure：`8/27`；
- budget exhausted：`6/27`；
- no candidate：`1/27`；
- 达标 checkpoint：`5/9`，低于预注册的 `6/9`；
- budget exhausted：`6/27`，高于预注册的不超过 `3/27`。

因此正式决定保持 `stop_before_dynamic_budget_controller_implementation`。

## Evaluated failure 分解

| 机制 | arms | 直接证据 | 解释 |
| --- | ---: | --- | --- |
| Clean replay source fetch 失败 | 5 | `cxxopts-r2` 为 peer receive failure；`libestr-r2`、`tiny-aes-c-r2`、`libfastjson-r2`、`libtommath-r2` 为 GnuTLS handshake termination | 候选已提交并通过前置层，失败发生在 exact-commit replay 重新访问 GitHub 时。正式 strict 仍为失败；不能假设网络正常时一定成功。 |
| Replay recipe 缺少前置生成步骤 | 2 | `libfastjson-r1/r3` 的 `/repro/build.sh` 直接执行 `./configure`，fresh exact commit 中该文件不存在，exit 127 | Agent 在恢复后的 workspace 中利用了 checkpoint 已生成的 `configure`，但复现 recipe 没有包含 `autogen.sh`/`autoreconf` 前置闭包。这是 continuation 与 fresh replay 之间的状态闭包缺口。 |
| 候选产物集合不合格 | 1 | `kilo-r2` 提交 `libkilo.a` 与 `kilo`；静态库有效，但 `kilo` smoke 失败，S2 为 `candidate_artifact_set_mismatch` | Agent 生成了部分有效交付，但额外提交的可执行物使整个候选无法通过严格裁判。 |

## 其余非成功终态

- 6 个 budget-exhausted arms 都在一次已完成请求后超过 300,000 recorded-token 单臂上限；token accounting 完整且预算守恒，但按协议不能再创建下一请求。受影响 checkpoint 为 `CLI11` 三次、`cxxopts` 两次、`kilo` 一次，说明长尾主要集中在 CMake header-only 与深层 Make continuation。
- `kilo-r3` 在 build 成功后执行工具检查时触发 `UnicodeDecodeError`，未形成 candidate。冻结 runner 将其记为 `no_candidate`，不是正式 `infrastructure_error`；只读机制分析仍应把它视为工具输出解码干扰，不能解释为 Agent 主动拒答。

## 可以与不能得出的结论

可以得出：固定 Agent continuation 在 5 个 checkpoint 上达到至少 `2/3` strict，但没有满足进入动态预算 controller 的稳定性、跨系统覆盖、深度覆盖和预算尾部门槛。继续直接实现 controller 会把 replay 网络、recipe 闭包和工具解码缺陷混入策略效果。

不能得出：`12/27` 是纯 Agent 能力成功率；5 个网络失败在无网络故障时会成功；动态预算机制无效；Jev 路由无效；自然失败或开放世界上的 Agent continuation 具有同样表现。

## 后续决策门槛

若继续该路线，应先用零 Provider 工程门禁证明：clean replay 从绑定 source snapshot 获取源码而不依赖运行时 GitHub；replay recipe 包含 checkpoint 之前影响 fresh build 的必要前置步骤；Docker/tool 输出按 bytes 捕获并以有界替换策略解码。三项通过后只能创建全新 identity 复核，不得修改或补跑 v2。

若不继续复核，则将 v2 作为固定 Agent continuation 的资格负结果封口，保留已经成立的 Jev 受控失败路由与混合 Workflow 结论，并重新选择论文下一项可证伪问题。

## Evidence

- Raw evidence：`.compile-sessions/benchmark-evidence-agent-continuation-qualification-v2`；
- Inventory canonical SHA-256：`9d749bf76571429b3fb6e7e325e61c1168df78e18e5ffa72d4457caff9c75465`；
- Q2 result SHA-256：`7c716b0170e031af706ce4a269dc475d4c0d7fc3afd3fa76b8af3fd63f244fe1`；
- Canonical result：`benchmarks/reports/cpp-agent-continuation-qualification-v2.{json,md}`。
