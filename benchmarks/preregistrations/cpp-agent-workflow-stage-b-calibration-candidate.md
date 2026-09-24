# Forge 单 Agent Workflow Node Stage B 六项目内部校准候选

## 状态与用途

- 状态：Phase 5 未授权执行候选；Issue #289。
- 用途仅限工程校准、轨迹分析和判定协议校准，不形成 Forge 相对 CXXCrafter 的无偏成功率。
- 本候选不授权 provider 请求、credential 读取、模型创建、Docker physical attempt、正式 evidence 写入或 model token。
- 候选代码合并后必须派生新的 authorized identity，冻结 release commit 和 Docker image ID，再执行唯一 reachability 与六项目 batch。

## 历史基线

- 历史来源为 CXXCrafter `stage-b-canary-v2`、`stage-b-external-v2` 和定向修订 `stage-b-external-uwebsockets-v3` 的综合裁决。
- Forge 只保存最小只读 audit fixture，不导入历史 outcome 到 Phase 5 方法结果，不修改 CXXCrafter evidence。
- 历史四层计数固定为 generated `6/6`、submitted `4/6`、strict S0-S5 `6/6`、bitwise `5/6`。
- `cppitertools` 与 `uwebsockets` 是历史 candidate-to-submit gap；该标签只定义审计分层，不改变 Phase 5 执行顺序、预算或终止规则。

## 六项目与顺序

固定顺序为：`yyjson`、`cppitertools`、`openh264`、`uwebsockets`、`c-ares`、`libass`。每个项目只有一个 physical attempt，不 replacement、不 backfill、不按历史结果重排。Repository、exact commit、构建系统、target contract 和功能 oracle 全部进入 manifest identity。

## 候选运行策略

- Provider/profile：DeepSeek `deepseek-flash`，endpoint `https://api.deepseek.com`。
- 单请求 timeout `300` 秒，provider retry `0`，fallback 禁止。
- 每项目最多 24 次模型请求、300,000 recorded tokens、64 agent steps、48 tool calls、32 commands。
- node/evaluator/replay timeout 分别为 1,800/1,800/1,800 秒，cleanup reserve 为 120 秒。
- 六项目 batch recorded-token ceiling 为 1,800,000；只在当前 attempt 完成 evaluator、finalize、cleanup 和 orphan 检查后决定是否创建下一 attempt。
- 任何 identity、reachability、evidence hash chain、Session terminalization、cleanup 或 orphan 不变量失败时停止；不 replacement、不 fallback。

## 结果层次

每个项目独立报告：

1. `candidate_generated_observed`
2. `candidate_submitted`
3. S0-S5 与 `strict_reproducible_build_success`
4. `bitwise_reproducible`

`submitted` 不等于 strict success；功能 replay 通过也不等于 bitwise。只读 trajectory audit 不回填正式提交结果。

## 通用实现边界

- 六项目差异仅通过冻结输入、target contract 和 oracle 表达。
- 不根据单项目结果修改公共 compiler prompt、工具、budget 或终止规则。
- 若发现必须修复的通用机制缺陷，关闭当前 identity，提交通用修复并以新 identity 重新校准。
- 项目专用补丁不得进入公共 Agent node。
- Stage C 在 Phase 5 六项目完整终态和决策包形成前保持阻断。
