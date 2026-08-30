# R3 Make jobs 真实 lifecycle 零 provider 门禁

- Issue：[#214](https://github.com/WWFXL/Forge-AutoCompiler/issues/214)
- 性质：运行前冻结的工程与构造效度门禁，不是模型实验，也不写正式 evidence。
- 上游：#202 Make P2 reference、#204 真实 lifecycle、#212 R3 Make 动作可达性。

## 研究问题

在同一 hoextdown commit、镜像、目录、target、stage 与 repair packet 下，R3 公开动作面允许的两种 direct Make 命令，是否都能在 production Compile Session 中把 opaque parent 的 P2 从 `unproven/opaque_wrapper` 转为 `proven/direct_make`，并通过 candidate verification 与 clean replay？

## 冻结 profile

1. `jobs-omitted`：`make libhoedown.a`
2. `jobs-1`：`make -j1 libhoedown.a`

二者都必须在 `/workspace/repo` 执行；stage 独立固定为 `cp libhoedown.a /artifacts/libhoedown.a`。禁止复用 #204 的 `-j2` 作为 R3 结果。

## 验收标准

- parent：`build_system_unproven`，不启动 replay；
- baseline：保持同一失败分类；
- treatment：P2 为 `proven/direct_make`；
- candidate 与唯一 clean replay 均通过；
- R0 分类、产物 identity 与双臂前缀历史完整；
- cleanup 后无 `deerflow-compile-*`、`deerflow-replay-*` 或 capture label orphan；
- 两个 profile 独立通过，不能以其中一个替代另一个。

## 外部影响边界

固定为 0 provider call、0 credential read、0 formal physical attempt、0 model token、0正式 evidence write。双臂同源恢复沿用 #204 的本地 SQLite checkpointer，仅作为零 provider lifecycle 测试设施。只使用 Ubuntu WSL2 原生 `docker.service`，不得启动 Docker Desktop。
