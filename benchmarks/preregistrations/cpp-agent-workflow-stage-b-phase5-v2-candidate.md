# C++ Agent Workflow Stage B Phase 5 v2 未授权候选预注册

日期：2026-09-25。追踪：Issue #291、Issue #294。

## 目的

本候选为首次 Phase 5 停止后的新实验身份。它只冻结已经完成人工执行的 exact-commit build-system qualification，以及 Runtime v7、external evaluator v2 和六项目任务合同。它不续跑、替换或回填首次 Phase 5 batch，也不导入首次 Phase 5 outcome。

## Qualification 来源

- plan：`benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v2-qualification.json`
- plan canonical SHA-256：`5f06941f19183117ba542099f0b3e9deb2c15d53798ef175812b5398d9769070`
- result：`benchmarks/fixtures/agent-workflow-stage-b-phase5-v2-qualification-result.json`
- result SHA-256：`df98e57edfea7b42911e8008534b94a62261aa93d7c3d20ae36f6ee8f8343125`
- qualification release：`1269d34ccb58f3545ffbd5469c141d321cdc1246`
- image ID：`sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`
- 边界：0 Provider request、0 model、0 formal attempt，执行前后均为 0 managed resource。

冻结的构建系统顺序如下：

| task | capabilities | selected |
|---|---|---|
| `yyjson` | `cmake` | `cmake` |
| `cppitertools` | `cmake` | `cmake` |
| `openh264` | `make` | `make` |
| `uwebsockets` | `make` | `make` |
| `c-ares` | `cmake`, `autotools` | `cmake` |
| `libass` | `autotools` | `autotools` |

## 执行合同

- Node input 必须接收完整 `build_system_capabilities`；Session 必须使用冻结的 `selected_build_system`。
- 正式执行在创建模型前必须复核 manifest、qualification result digest、exact commit、image ID、运行时探测结果和 0 managed orphan。
- evaluator 固定为 `external-evaluator-v2`，使用 delivery/candidate/target 三集合规则及显式 executable oracle policy。
- evidence 使用独立目录 `/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v2`，attempt、thread、evaluation 和 document type 均使用 v2 身份。
- 任务顺序、预算、Provider candidate、target contract 和 oracle 保持首次 Phase 5 预注册值；不根据 qualification 或历史 outcome 修改。
- Stage C 保持未授权。

## 当前授权边界

本 candidate 的 Provider、credential、model、reachability、Docker、evidence 和 formal attempt 授权全部为 false，token ceiling 为 0。当前 runner 只允许 `validate` 和 0 Provider `preflight`；`reachability` 与 `batch` 必须 fail closed。

真实执行前必须派生独立的 authorized amendment，冻结合并后的 release revision，并在该修订中实现 create-once evidence 生命周期。candidate 的生成或合并本身不构成真实实验授权。
