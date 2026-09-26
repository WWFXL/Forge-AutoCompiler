# Stage C v3 失败审计

Stage C v3 identity `410f32b0a2cf22eac9023c80da18876adee5fbd6f2abd689eac37ce63e8f2b29` 在 `main@cbb29c2473fdb0814ed4a47bdd7ea4f06fc21f28` 上执行。唯一 reachability 通过，消耗 1 request / 79 recorded tokens。

`stage-c-v3-json-c-r1` 是唯一闭合 pair。A 臂消耗 3 requests / 30,689 recorded tokens，生成并提交候选，但因 oracle 的跨容器路径挂载错误在 S3 失败；B 臂在 0 次模型调用前因非规范 `cmake-configure` 能力值触发 `AgentWorkflowContractError`。两臂均完成 cleanup，pair 以 paired delta 0 闭合。

下一项 `stage-c-v3-stockfish-11-r1` 在 pair source 校验阶段失败。冻结源码只有 `src/Makefile`，v3 顶层限定 probe 报告 `stockfish-11 build-system identity 漂移`。该 pair 没有目录、attempt 或 result。

v3 合计形成 2 个正式 arm attempt、4 次 Provider 调用（含 reachability）和 30,768 recorded tokens。evidence 包含 243 个文件、1,514,018 bytes；没有未闭合 pair或 managed resource 残留。

v3 必须永久停止。v4 不导入 v3 outcome，使用新的 pair、attempt、reachability、batch marker 和 evidence 目录重新执行完整设计。
