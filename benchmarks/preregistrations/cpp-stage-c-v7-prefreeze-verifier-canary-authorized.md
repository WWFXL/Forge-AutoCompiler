# Stage C v7 pre-freeze verifier authorized canary 预注册

日期：2026-09-27。追踪：[Issue #343](https://github.com/WWFXL/Forge-AutoCompiler/issues/343)。

## 授权对象

本阶段从已合并的 Stage C v7 未授权 candidate 派生独立 authorized identity。父 manifest canonical SHA-256 固定为 `80de8fa1ca05910384570920bd67762935f67c2567c4c905a40c86232ed73983`，授权基线固定为 `main@d8f0e24ad78396396150bde8099c9a619b5e9306`。v5/v6 evidence 和 v7 candidate 均保持只读，不导入历史 outcome，也不在原目录追加文件。

## 固定执行顺序

唯一批次按 `theora -> json-c -> libjpeg-turbo -> oatpp` 运行四个 Forge B 臂 attempt。每个 task 使用新的 thread、Compile Session、attempt marker、result 和 token ledger。任一 attempt 未达到 strict external-evaluator-v4 success，立即停止后续 task；禁止 retry、replacement、backfill、追加 schedule 或把旧 attempt 解释为本批结果。

正式执行前只允许一次 DeepSeek `deepseek-flash` reachability。它必须精确返回冻结文本、actual model 匹配、非 streaming、0 retry、无 fallback；失败即停止，不创建 batch marker。

## 运行链路

- Agent runtime 固定为 `run_agent_workflow_node_v3(...)`，pre-freeze functional oracle 由 system-owned registry 注入。
- Candidate create-once 冻结前执行完整 delivery scan、唯一 target mapping 与 functional oracle；拒绝只返回排序去重的结构化 code/evidence，允许同一 physical attempt 修复并重提。
- Candidate 冻结后独立调用 `run_external_evaluator_v4(...)` 完成 S0-S5、oracle、clean replay、bitwise delivery 和 cleanup 判定。
- 每个 attempt 无论模型、candidate 或 evaluator 成败都必须执行 cleanup/finalize；结束后 managed compile/replay container、paused container 和 managed image 必须为 0。
- 恢复只接受已经形成 completed marker、result、cleanup 和连续顺序的 attempt 前缀。已失败 marker、顺序缺口或交叉 identity evidence 一律 fail closed。

## Token 与操作边界

Recorded token 没有总量、reachability 或逐 attempt 上限。每个成功 Provider 响应逐条记录 `input_tokens`、`output_tokens` 和 `total_tokens`，累计 token 只用于报告，不触发停止。每个 attempt 仍保留最多 24 个模型请求、64 个 Agent step、48 个工具调用、32 条命令和冻结墙钟/命令/evaluator/replay/cleanup 时限。

`validate` 不读取 credential、不创建模型、不连接 Docker、不写 evidence。`preflight` 是真实执行命令的一部分，只检查 credential 环境变量存在性，并同时核验干净 `main == origin/main`、授权基线祖先关系、网络介质、Linux Docker endpoint、精确 image ID、空 evidence 和 0 managed resources。Credential 值、Provider 响应正文和原始 oracle 输出不得进入报告。

## 结果口径

每条 result 必须记录模型请求数、逐响应 token ledger、命令/工具/step 数、submit 次数、结构化 rejection code/evidence 数量、是否观察到同 attempt repair、candidate identity、S0-S5、bitwise replay、cleanup 和错误分类。Batch report 只给出工程 canary 的描述性终态，不估计 A/B treatment effect、不计算 p 值、不排名模型，也不替换 v5/v6 结论。

本 PR 只实现 authorized runner 与零 Provider 门禁。真实 Provider reachability 和四条 canary 必须等本实现合并后，从符合 preflight 的干净主干显式执行。
