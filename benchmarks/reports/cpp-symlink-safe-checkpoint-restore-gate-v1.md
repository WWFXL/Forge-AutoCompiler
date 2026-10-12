# Symlink-safe checkpoint restore gate v1

**决定：`proceed_to_dynamic_budget_trajectory_qualification_v5_design`。**

状态：`passed`；门禁通过 `8/8`。

## 门禁结果

| Case | 通过 |
| --- | --- |
| `legal_parent_relative_symlink` | 是 |
| `escaping_relative_symlink` | 是 |
| `absolute_symlink` | 是 |
| `escaping_hardlink` | 是 |
| `character_device` | 是 |
| `fifo` | 是 |
| `tree_hash_mismatch_not_published` | 是 |
| `v4_libestr_checkpoint_round_trip` | 是 |

## 结论边界

本门禁是工程修复验证。通过只说明合法 libtool 相对符号链接能够安全恢复，并解除全新 v5 轨迹资格的基础设施阻塞；不评价动态预算、Jev、Agent 或 controller 效果。

v1-v4 identity、runner、报告与 raw evidence 均保持只读；本门禁未续跑 v4。
