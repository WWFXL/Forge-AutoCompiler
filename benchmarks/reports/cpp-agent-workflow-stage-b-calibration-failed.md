# Forge 单 Agent Workflow Node Phase 5 停止结果审计

> 本报告由只读分析器从冻结 manifest、append-only marker/result 和停止 Session 确定性生成。

## 结论

- 唯一 reachability 通过：1 request / 61 recorded tokens。
- 完成 4/6 个项目结果；第 5 个项目 `c-ares` 在模型调用前因 build-system identity drift 停止。
- generated=4，submitted=4，strict=1，bitwise=1。
- batch 使用 545,484 tokens；含 reachability 共 545,545/1,805,000。
- batch marker 为 failed；未生成 batch report 或 Stage C 决策包，Stage C 保持阻断。

## 项目结果

| 项目 | Attempt | Generated | Submitted | S0-S5 passed | Strict | Bitwise | Tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| `yyjson` | completed | true | true | 2 | false | - | 133,186 |
| `cppitertools` | completed | true | true | 2 | false | - | 155,645 |
| `openh264` | completed | true | true | 6 | true | true | 94,031 |
| `uwebsockets` | completed | true | true | 3 | false | - | 162,622 |
| `c-ares` | stopped_before_model | - | - | - | - | - | 0 |
| `libass` | not_attempted | - | - | - | - | - | 0 |

## 停止点

- `c-ares` exact commit `589b5887d47736e5b70a1fddaf9bf90297adde65` 检出成功。
- manifest 冻结 `autotools`，Forge 探测器记录 `cmake`；模型调用未开始。
- 未执行后续项目：`libass`。
- 停止后 0 managed compile/replay container、0 managed image、0 paused parent。

## 解释边界

- 结果仅用于工程校准和失败机制审计，不构成无偏成功率或模型排名。
- 原 batch 不重跑、不 replacement、不 backfill；任何后续执行必须采用新 identity 和新预注册协议。
- 新协议至少需要修正 c-ares build-system identity，并为服务型 executable 定义不会触发三个 600 秒通用 smoke 的验证合同。

## 复算

```bash
python scripts/forge_agent_workflow_stage_b_calibration_result.py
```
