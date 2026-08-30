# R3 Make 单配对未执行 candidate

- Issue：[#216](https://github.com/WWFXL/Forge-AutoCompiler/issues/216)
- 性质：零 provider、零 Docker、未执行候选；不是 #208 retry、replacement、backfill 或 extension。
- 父证据：#208 R2 execution 只读结果；#212 action alignment；#214 真实 lifecycle。

## 候选问题

在 hoextdown case、九字段 repair packet、`baseline -> treatment`、state matching 和预算不变时，公开且双臂共享的 R3 action surface 能否支持未来的单配对 conversion replication？本阶段只验证 runner 接线，不估计 treatment effect，也不产生模型行为结果。

## 冻结动作面

- build 只能 direct `make/gmake`，目录 `/workspace/repo`，target `libhoedown.a`；
- jobs 可省略或为 `1..2`，拒绝无界、0、超限和非法值；
- stage 必须独立执行，只允许 `libhoedown.a -> /artifacts/libhoedown.a`；
- repair packet 仍是唯一 treatment exposure；双臂共享相同工具描述、validator、预算和 R0 companion 合同。

## 授权与停止规则

Checkpoint、reachability、provider、credential、Docker、pair 和 evidence write 全部未授权，model-token authorization 为 0。Runtime adapter 只提供 `validate`、`plan` 与只读 Git `preflight`；任何 execute 入口必须 fail-closed。只有本候选合并且 release preflight 通过后，才能另建 execution amendment，并再次明确是否授权 provider 调用。
