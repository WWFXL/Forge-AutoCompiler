# 同阶段异根因类型化语义路由 benchmark v2 预注册

## 身份与研究问题

- identity：`cpp-typed-semantic-routing-pilot-v2`
- tracking Issue：[#391](https://github.com/WWFXL/Forge-AutoCompiler/issues/391)
- 工作类型：零 Provider benchmark 难度资格审计
- 后续候选：Jev 类型化语义路由

本阶段回答：在 CMake、Make、Autotools 中，当 coarse phase facts 完全相同时，真实失败日志能否区分需要不同最优恢复动作的根因，并且该任务是否没有被只看阶段事实的固定规则或项目族隔离的浅层文本分类器饱和。

本阶段不评价 Jev。Provider 调用、credential 读取、模型调用和模型 token 均为 `0`；不实现 controller，不创建 Jev 请求，不校准 confidence，不修改或续跑 v1 与任何历史 evidence。

## 结果盲项目冻结

冻结 6 个未进入 v1 的公开 project family，CMake、Make、Autotools 各 2 个：

| 构建系统 | 项目 |
|---|---|
| CMake | `args`、`yyjson` |
| Make | `hoextdown`、`hiredis` |
| Autotools | `c-ares`、`numactl` |

项目、exact commit、source archive SHA-256、license SHA-256、构建配方、产物合同、functional oracle 和故障输入文件以 `benchmarks/fixtures/cpp-typed-semantic-routing-pilot-v2-source-pool.json` 为准。

正式 outcome 前的项目可行性筛选不进入 outcome matrix：

- `libcheck`：固定 Stage C image 缺少 `makeinfo`；
- `jpegoptim`：固定 image 缺少 `libjpeg-dev`；
- `libusb`：reference build/oracle 可闭合，但从 `git archive` 开始的 clean replay 缺少 `.git`，上游 `gen-describe.sh` 生成 `Unknown source`，使 bitwise static-library 比较不稳定。

这些排除在项目池冻结前完成。正式执行后不得替换项目、删除失败项目或只保留成功状态。

## 统一状态与隐藏故障

每个项目构造 3 个状态，模型可见的 phase facts 固定为：

```json
{
  "source_available": true,
  "configured": true,
  "build_attempted": true,
  "build_succeeded": false,
  "artifacts_staged": false,
  "functional_oracle_passed": false,
  "strict_verifier_passed": false
}
```

隐藏故障为：

1. `missing_compile_input`：删除实际参与编译的源码或头文件，再执行正常 build；
2. `invalid_build_state`：破坏生成的 build state，再执行正常 build；
3. `wrong_build_target`：执行不存在的 opaque target，不留下持久修改。

state ID 使用 opaque SHA-256 前缀。故障类别保存在独立 hidden mapping 中，不进入 `model_input`。模型输入只含 state ID、构建系统、统一 phase facts、原始失败日志尾部、候选动作族和剩余预算。失败触发命令、candidate bound command、候选顺序和 state ID 不得包含三个故障类别字符串。

## 候选动作与真实 outcome

每个状态固定按以下顺序提供完全相同的动作族：

```text
dependency, configure, build, escalate_agent
```

动作命令由代码按项目预绑定，不由模型生成。同一项目三个状态的四组 bound command 必须完全一致。

- `dependency`：恢复冻结的编译输入；
- `configure`：重建或恢复构建系统生成状态；
- `build`：执行正常构建目标；
- `escalate_agent`：本 pilot 使用零 Provider 的确定性通用恢复 surrogate，先恢复输入再重建配置。它只保证存在兜底路径，不代表真实 Agent 效果。

每个候选动作从同一故障 checkpoint 的隔离副本开始。动作成功后执行冻结 continuation：

```text
normal build
-> artifact stage
-> functional oracle
-> exact-commit provenance
-> clean replay
```

`strict_success` 只有在 continuation 与 candidate、functional、provenance、clean replay 全部通过时成立。任何 direct action 都不能跳过严格终点。

## 标签与重复

每个 project/state/action 执行两次独立 replay，共 `6 * 3 * 4 * 2 = 144` 个 action branch；另执行 12 个 reference closure。失败、timeout 和部分执行全部保留。

动作成本在结果前冻结：

| 动作 | 成本 |
|---|---:|
| `build` | 1 |
| `configure` | 2 |
| `dependency` | 3 |
| `escalate_agent` | 4 |

标签只由 outcome matrix 生成：先保留两次 replay 都达到 strict success 的动作，再选择冻结成本最低者。成本各异，因此成功集合非空时最优动作唯一。旧 Agent 行为、故障注入类别和人工预期不作为标签。

categorical replay signature 只含 action/continuation exit class 与 strict success；日志文本、耗时和非 bitwise executable 字节不进入一致性判定。

## 零 Provider 基线

### RuleGate

RuleGate 只读取统一 phase facts、候选动作族和冻结成本。由于所有状态输入相同，它固定选择最低成本的 `build`。报告 top-1 最优动作准确率和所选动作达到 strict success 的 route-acceptable coverage。

### TF-IDF / 逻辑回归

输入只使用 `semantic_failure_log`。固定 word unigram/bigram、sublinear TF、最多 5000 特征，以及 one-vs-rest 包装的 `C=1.0` liblinear 逻辑回归；按 project family 执行 leave-one-project-family-out，六折预测合并后计算 top-1。不得在结果后改变 tokenizer、正则化、特征或 split。

## 资格门槛与停止规则

以下条件必须全部满足：

- 6 个项目各两次 reference build、oracle、provenance 和 clean replay 闭合；
- 18 个状态、144 个 action branch 完整且全部有界终结；
- state/action categorical replay 一致率至少 95%；
- 三个构建系统各形成 6 个同 facts 状态，并同时出现 `dependency`、`configure`、`build` 三类最优动作；
- `dependency`、`configure`、`build` 各至少在两个 project family 中成为唯一最优；
- RuleGate top-1 严格低于 75%；
- RuleGate route-acceptable coverage 严格低于 90%；
- LOPO TF-IDF/逻辑回归 top-1 严格低于 95%；
- 没有 fault identity、候选顺序、bound command 或 state ID 直接泄露标签。

全部通过时决定为 `proceed_to_jev_offline_qualification`。任一条件失败时决定为 `stop_jev_provider_qualification`。不得结果后降低阈值、修改故障模板、改变成本、调文本基线、替换项目或在同一 evaluation 数据上挽救。

## 解释边界

通过只证明 v2 benchmark 具有进入独立 Jev 离线资格实验的可辨识空间，不证明 Jev 有效。失败说明本次受控故障设计仍被规则、模板或执行不稳定性解释，不说明 Jev 不适合自动化编译。

本 pilot 不支持 confidence 校准、费用优势、严格成功非劣、端到端 controller 效果、模型排名或通用路由创新主张。
