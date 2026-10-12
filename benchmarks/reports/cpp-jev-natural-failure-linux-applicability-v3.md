# Jev 自然失败 Linux applicability v3 结果

- 状态：`completed`
- 决定：`stop_natural_failure_linux_applicability_v3`
- 原始搜索结果：200；未见候选：197
- Linux-applicable 仓库：79；基础设施失败：0
- 平台不合格边：7；ambiguous 边：0
- build / Docker / credential / Provider / model token：0 / 0 / 0 / 0 / 0

## 分配配额

| 构建系统 | 合格分配 | 要求 |
| --- | ---: | ---: |
| cmake | 0 | 12 |
| make | 0 | 12 |
| autotools | 8 | 12 |

## 冻结项目

| 系统 | reserve 排名 | 项目 | exact commit |
| --- | ---: | --- | --- |
| autotools | 1 | `vectorgraphics/asymptote` | `d81a6a56ff21a968a3628f50cb439531f6cfd998` |
| autotools | 2 | `steveicarus/iverilog` | `be5984bb993642c116a07cef7fb9dc1420372c62` |
| autotools | 3 | `swfans/syndwarsfx` | `5d27312015f19c13ae2cc83fdf7f5e15de4ba434` |
| autotools | 4 | `tpm2-software/tpm2-abrmd` | `d2aa554c812341e76f396f591e020e62cd947f7f` |
| autotools | 5 | `blue-panels/mcommander` | `b408f1f6875cada759dd0717e7a712dfc3bffa2d` |
| autotools | 6 | `gpg/libgcrypt` | `df7af3571744bc8d0d45b46c5b73f300ee447410` |
| autotools | 7 | `lxin/quic` | `58807ee464ed4452ebd0f0159dfa81f326b1236c` |
| autotools | 8 | `utelle/sqlite3multipleciphers` | `441fd8c98f691d9d53033ac456f80f082ba447f8` |

## 解释边界

本结果只评价 source-only Linux applicability 必要条件与采集隔离。它没有运行构建，不证明
Linux 构建成功、自然失败或 reference closure，也不评价 Jev、Agent、动作路由、成本收益或
动态预算控制。后续必须先做 build + reference qualification，再分配实验角色。
