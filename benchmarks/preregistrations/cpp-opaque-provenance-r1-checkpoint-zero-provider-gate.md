# Opaque build provenance R1 独立 checkpoint 真实 Docker 零 provider 门禁

本门禁承接 Issue #196 / PR #197 已发布的 `yyjson` 未授权候选。当前只验证一个真实 controlled parent 能否形成可复用的 message/environment/budget checkpoint，并在派生 state-matched 双臂后完成 cleanup；不执行模型 continuation，不写 #196 候选 evidence。

## 冻结 case 与 parent

- 仓库与 exact commit：`https://github.com/ibireme/yyjson@9365ddc7061033df656578bf86040048b5b5531a`。
- CMake build directory / target：`/workspace/repo/build` / `yyjson`。
- Output / staged artifact / type：`build/libyyjson.a` / `libyyjson.a` / `static_library`。
- Parent 使用单一顶层 `sh -c` wrapper 完成 configure、build 和 stage。Wrapper 可进入候选 replay，但不提供 trusted direct-CMake identity，因此 P2 必须保持 `unproven / opaque_wrapper`。
- Parent submit 必须通过真实 bound `_submit_with_post_build_phase`；失败后 fence 三字段全部释放，candidate 为 failed、replay 为 not_run。

## Checkpoint 与 R0

Checkpoint 捕获点保持 `after-neutral-tool-message-before-continuation`。Message、environment 与 budget 绑定到同一 capture ID；双臂的 workspace/artifacts/image 和剩余预算必须 canonical 相同，唯一 treatment exposure 是原 repair packet。

Issue #194 R0 observability 是本门禁的前置条件。静态 gate 必须重新证明 `agent.tool_rejection_observed`、历史七字段兼容、五个原子 observation 字段和 raw-command 禁止规则；真实 Docker gate 不伪造模型 tool call，也不为未执行的 arm 写 companion event。

## 执行与停止规则

- 只允许 WSL Ubuntu 原生 Docker Engine；环境变量 `FORGE_RUN_OPAQUE_PROVENANCE_R1_CHECKPOINT_DOCKER=1` 显式开启唯一真实 gate。
- 固定 0 provider、0 formal attempt、0 model token、0 credential read、0 #196 candidate evidence write。
- Clone、parent build、submit、capture、arm provisioning 或 cleanup 任一失败即停止；禁止 replacement/backfill。
- Cleanup 必须删除 parent/arm Compile Session 容器、checkpoint helper、continuation image 和 snapshot，最终 capture label 及 `deerflow-compile-*` / `deerflow-replay-*` 均为 0 orphan。

本门禁成功只证明独立 checkpoint 和未来 intervention delivery 的基础设施可达，不构成 repair packet 或模型效果证据。Reachability 与单 pair 仍须另建 execution amendment。
