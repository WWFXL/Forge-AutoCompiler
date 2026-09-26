# Stage C v5 正式结果审计

日期：2026-09-27。追踪：Issue #329。正式 identity 为 manifest canonical SHA-256 `11eefa99737b6e20fdf5d300802cf5a7cf0a9178a5f0a44de4028693721859a2`，release 为 `c37a145c3b0b30453cb2053a8fca3dd2d3599435`。

## 执行完整性

- 唯一 reachability 通过：1 request / 73 recorded tokens，模型为 `deepseek-flash`。
- batch marker 为 `passed`；24/24 pairs、48/48 arms 全部闭合。
- 正式 arms 共 331 requests / 3,131,424 recorded tokens；含 reachability 共 332 requests / 3,131,497 tokens。
- deployment report SHA-256 为 `61b2a387d7b57adfca8c0debf7110ffdc78d61f120749b2e53da0c570bdb6b7b`，paired report SHA-256 为 `9e732c22237dc41535b007dd1274aabbd3d44340cccae2e0a6e00af987783046`。
- evidence 共 23,219 个文件、1,049,568,450 bytes；排序后的相对路径与文件 SHA-256 清单摘要为 `f114e4641a61bdb5ecd7eb809a96deaa5a410d661016581c9b95f94a4ef91c05`。
- 执行结束后 Stage C managed container/image 均为 0。

## 主要结果

| 指标 | A：CXXCrafter controlled | B：Forge Agent Workflow v2 |
|---|---:|---:|
| attempts | 24 | 24 |
| candidate generated / submitted | 24 / 24 | 22 / 22 |
| external evaluator 完整结果 | 24 | 16 |
| strict success | 19 | 0 |
| bitwise true / false / unavailable | 19 / 0 / 5 | 0 / 15 / 9 |
| model requests | 88 | 243 |
| recorded tokens | 842,776 | 2,288,648 |

预注册配对差定义为 `success_B - success_A`。19 个 pair 为 `-1`，5 个为 `0`，没有 `+1`；12 个独立项目的平均 score 为 `-0.7916666666666666`。其中 8 个项目 score 为 `-1.0`，`libjpeg-turbo`、`leveldb`、`oatpp` 为 `-0.5`，`libsoundio` 为 `0.0`。

## 分层结果

| Arm | S0 | S1 | S2 | S3 | S4 | S5 |
|---|---:|---:|---:|---:|---:|---:|
| A passed | 24 | 24 | 24 | 19 | 24 | 19 |
| A failed | 0 | 0 | 0 | 5 | 0 | 5 |
| B passed | 16 | 16 | 12 | 15 | 15 | 0 |
| B failed | 0 | 0 | 4 | 1 | 1 | 16 |
| B unavailable | 8 | 8 | 8 | 8 | 8 | 8 |

A 臂的 5 个失败均落在 S3 与 S5：`libsoundio` 两次、`oatpp` 第一次、`libjpeg-turbo` 第二次、`leveldb` 第二次。B 臂有 6 次方法错误和 2 次未生成候选，因此没有进入完整 external evaluator；其余 16 次全部在 S5 失败，没有严格成功。

## 结论边界

本轮证明此前的 Stockfish 嵌套 `src/Makefile`、Git 获取以及带点号任务的安全 Session identity 修复均可支撑完整正式批次。结果显示冻结条件下 A 臂明显优于 B 臂，同时 B 臂消耗更多请求和 tokens。

Stage C 是校准性描述实验。24 个 pair 来自 12 个项目的双重复，不能当作 24 个独立项目；本报告不作显著性、总体无偏成功率或超出冻结任务集合的泛化声明。原始 evidence 保持只读，机器可读汇总见 `benchmarks/reports/cpp-stage-c-paired-calibration-v5-result.json`。
