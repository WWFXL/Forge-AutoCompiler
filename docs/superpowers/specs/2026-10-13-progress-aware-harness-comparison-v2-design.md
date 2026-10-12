# 进展感知结构化 Harness H0/H1 配对比较 v2 设计

## 失败驱动修订

v1 的 Q0 9/9 strict，Q1 6/6 arms 分类与计量闭合，但派生 metrics 递归搜索到主 Agent 和 evaluator 两份 `events.jsonl` 后返回空列表，把 H1 snapshot/compaction 错记为 0。主 Agent raw events 证明三个 H1 arms 实际分别存在 5、6、7 个 snapshot，与请求数一致；H0 为 0。

v1 停止在 Q2 前并以 inventory `3a03ec1a2bed0ab5311842ce51bc0292963871d2c9f3d9d364ce84aae51fa201` 封存。其 canary 不进入 v2 estimate。

## v2 唯一变化

v2 继承 v1 的 treatment、9 个 checkpoint、3 次重复、配对顺序、`deepseek-flash`、单臂与批次预算、state-1 离线 source archive、CandidateVerifier、S0-S5、分析阈值和停止规则。只修改：

1. Harness metrics 只读取不位于 `evaluations/` 下的唯一主 Agent `events.jsonl`；
2. Q1 要求 H0 snapshot/compaction 均为 0；
3. Q1 要求 H1 snapshot/compaction 均大于 0，且分别等于 model request 数；
4. v1 inventory 与 Q2 不存在状态成为 v2 前置门禁。

## 阶段与结论

v2 使用独立 create-once evidence，重新执行 Q0、Q1 和 Q2，不续跑或回填 v1。Q0 仍须 9/9 strict；Q1 仍为 3 pairs / 6 arms；Q2 仍为 27 pairs / 54 arms。主要与替代通过路径、解释边界均以 v1 设计为准。
