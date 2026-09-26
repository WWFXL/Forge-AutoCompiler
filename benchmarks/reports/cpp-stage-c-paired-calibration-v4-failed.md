# Stage C v4 失败审计

v4 `46d1f2f95a14042f035fb908d3f5460672d560ae26eabcaa66f823a5594b8189` 在 `9c271ea1d3b3b9dcec8e6aecbd16eab949b2a72b` 上运行。唯一 reachability 通过，消耗 1 request / 73 recorded tokens。

`json-c` 与 `stockfish-11` 的 replicate 1 pair 完整闭合；Stockfish 的 `src/Makefile` 已被正确识别。`rnnoise-0.1.1` A 臂闭合后，B 臂在 attempt 登记前创建 Compile Session 失败：pair ID 中的点号被直接复制进 thread ID，不符合安全路径组件合同。

v4 共形成 5 个正式 arm attempt、31 次 Provider 调用（含 reachability）和 213,374 recorded tokens。evidence 包含 887 个文件、7,190,319 bytes；停止后无 managed resource 残留。v4 必须永久停止，v5 不导入任何 v4 outcome。
