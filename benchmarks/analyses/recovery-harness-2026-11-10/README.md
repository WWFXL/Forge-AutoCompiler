# 2026-11-10 同初始方案恢复Harness比较分析

结果待用户审核；不修改论文。报告见[结果说明](../../../docs/research/2026-11-10-recovery-harness-comparison-results.md)。

- `summary.json`：36行、方法全成本、逐响应Token/费用复算；共同规划实际支付一次，两方法部署均计全额。
- `diagnostics.json`：实际重放attempt、验证长尾、原文件标签、恢复指导哈希与每次修订；继承的原analysis身份头差异明确披露。
- `results-by-slot.csv`：36槽可读表。main_build_completed只表示本轮主构建，不代表干净重放成功；author_tests不在本轮要求内。
- 两份Python脚本是实际只读分析的代码副本，保留当时绝对原件/会话路径；重算时把输出指向不存在的新分析目录，不能重写封存原件或原派生结果。

权威原件为`/home/yiwei/.codex/outputs/forge-recovery-harness-comparison-flash-v2`；运行revision为`7e439b51cfb7e1706959ed3a1a63b5821c7cf0d5`，inventory为`235feccd7e533f3077c9a33cc1f405e28875e0b426b743e015cfa30096fc40dd`。v1原规划已带origin导入一次，不能再和v1目录重复累计。报告和本目录是派生解释，不取代原件。

实际结果：H0/R1主构建16/18、15/18；可复现交付均11/18。每法实际replay14个：11过、2失败、1超时，另4未启动；未启动不当作replay执行失败。失败、未知原文件检查、费用及未通过原因完整保留。
