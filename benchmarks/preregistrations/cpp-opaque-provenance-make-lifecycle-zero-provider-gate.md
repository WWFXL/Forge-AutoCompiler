# Opaque build provenance R2 Make 真实 lifecycle 零 provider 门禁

本门禁承接 Issue #202 / PR #203 已发布的 Make P2 reference criterion。目标是验证真实 Compile Session 中的 Make opaque-provenance parent、state-matched 双臂、candidate verification、clean replay 和 cleanup 能否闭合；不执行模型 continuation，不创建正式实验 evidence。

## 冻结 case

- 仓库与 exact commit：`https://github.com/kjdev/hoextdown@1ef9a71957570c2a65b7daa1b2f693ad87daf385`。
- Build system / workdir / target：Make、`/workspace/repo`、`libhoedown.a`。
- Output / staged artifact / type：`libhoedown.a` / `libhoedown.a` / `static_library`。
- Case 逐字段继承 result-blind formal v1 source protocol；#202 Make evaluator SHA-256 固定为 `5df722d6115aa879a9dbe43fb5f98278ff72df6958ae99f22fe4cb2f6d16c14a`。

## Controlled parent

Parent 在 trusted runtime 中执行单一顶层 `sh -c` wrapper。Wrapper 内先 `make clean`，再构建真实 `libhoedown.a` target 并 staging 到 `/artifacts/libhoedown.a`。该步骤包含 clean replay 所需的完整构建与 staging 行为，但 trusted top-level executable 是 `sh`，因此不能证明 direct Make identity。

Parent 的 production submit 必须只因 `build_system_unproven` 失败；static P2 必须为 `unproven / opaque_wrapper`，candidate 与 replay 不启动。Submit 必须经过真实 bound post-build wrapper，失败后 supporting command、started-at 和 remaining-command fence 全部释放。

## 双臂与 treatment

Baseline 与 treatment 从同一个 message/environment/budget checkpoint 派生。两臂的 continuation image、workspace、artifact、parent command records 和剩余 budget 必须 canonical 相同；treatment 唯一额外 exposure 是白名单 repair packet。

Packet 固定 expected/selected build system、effective directory、target、`proof_status=opaque_wrapper` 与抽象 repair goal；禁止完整 Make 命令、argv、shell、prompt、solution 和 secret。

- Baseline 不追加 invocation，再次 submit 必须仍为 `build_system_unproven` 且 0 replay。
- Treatment append-only 执行 direct `make libhoedown.a -j2`，再 staging 同一 artifact；不得删除、重排或改写 parent history。
- Treatment 必须转为 P2 `proven / direct_make`，production candidate verification 和独立 clean replay 同时通过。

## 执行边界与停止规则

- 固定 0 provider、0 credential read、0 formal attempt、0 model token 和 0正式 evidence write。
- 只允许 Ubuntu WSL2 原生 Docker Engine；环境变量 `FORGE_RUN_OPAQUE_PROVENANCE_MAKE_LIFECYCLE_DOCKER=1` 显式开启唯一真实 gate。
- 不修改 production Compiler、Oracle、`operations.py`、#202 Make evaluator、冻结 CMake evaluator、历史 runner/manifest/evidence。
- Clone、parent build、submit、capture、arm provisioning、candidate/replay 或 cleanup 任一失败即停止；禁止 replacement/backfill。
- Cleanup 必须删除 parent、双臂、replay、checkpoint helper、continuation image 和 snapshot；capture label 与 `deerflow-compile-*` / `deerflow-replay-*` 最终为 0 orphan。

本门禁成功只证明 Make checkpoint 与确定性 treatment lifecycle 可达，不构成 repair packet 或模型效果证据。Reachability 与单 pair 必须另建 execution amendment。
