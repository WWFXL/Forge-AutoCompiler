# Jev 自然失败 Linux applicability v4 实施计划

日期：2026-10-12。追踪：Issue #415。设计：
`docs/superpowers/specs/2026-10-12-jev-natural-failure-linux-applicability-v4-design.md`。

## 阶段 1：冻结修复设计

- 固化 v3 的正式结果、构造效度审计和 5/7 误伤，不改写 v3 evidence；
- 冻结 endpoint/host-platform 两维分类、决策顺序和真实回归期望；
- 冻结 v1-v3 历史排除、800 条搜索上限、12/12/12 reserve 门槛和停止规则。

## 阶段 2：实现独立 v4

- 新建 v4 fixture、Schema、manifest、runner 和测试，不修改 v3 文件；
- 实现构建语言注释剥离、endpoint 信号、项目级文档排他信号和 Linux 文档正面信号；
- 将 regression fixture 纳入协议校验；
- 使用确定性最大二分匹配分配唯一项目族，并单独报告 eligible edge 与 allocation 数量；
- 从冻结 v2 catalog 与 v3 formal report 构造历史排除集合并验证哈希。

## 阶段 3：零执行验证

- 运行 v4 全部 fixture、source contract、故障隔离、最大匹配和报告/audit 测试；
- 同时运行 v3 与 v2 相邻回归，确认历史协议未改变；
- 验证 v3 正式 report、marker、evidence inventory 和 v1/v2 inventory 哈希未变化；
- 验证 candidate manifest 为 0 build、0 Docker、0 credential、0 Provider、0 token；
- 提交 implementation revision 后再冻结 execution authorization。

## 阶段 4：唯一 source-only attempt

- 在干净分支、固定 implementation revision、create-once 路径和 GitHub API/时间预算下执行一次；
- 逐项目保存 exact commit、tree、入口/文档 blob 哈希、typed signals 和最终分类；
- 审计 marker、report 哈希、inventory、regression qualification、eligible edge 和 12/12/12 allocation；
- attempt 创建后无论成功、失败或部分完成均只读，不重跑、不补齐、不替换。

## 完成标准

- 7 个 v3 真实排除边按冻结期望得到 5 个保留、2 个排除，原合成回归不退化；
- 正式 attempt 给出可复算的单一决定和完整资源边界；
- 若通过，只进入独立 build/reference qualification 设计；若失败，明确区分 classifier 失败、样本框不足或基础设施失败；
- 不调用 Jev/Agent Provider，不创建动作矩阵，不实现 controller，不写后续 build/reference evidence。
