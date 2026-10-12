# Jev 自然失败 Linux applicability v3 实施计划

日期：2026-10-12。追踪：Issue #415。设计：
`docs/superpowers/specs/2026-10-12-jev-natural-failure-linux-applicability-v3-design.md`。

## 阶段 1：冻结设计

- 冻结必要条件、信号来源、三分类、12/12/12 reserve 配额和停止规则；
- 冻结 `SketchyBar`、Windows-only、裸机交叉编译反例与多平台正例；
- 更新 `RESEARCH_STATUS.md`，明确本阶段是基础设施资格且 0 Provider。

## 阶段 2：实现候选

- 新建独立 v3 Schema、manifest 和 runner，不修改 v2 文件；
- 实现根入口/有界文档读取、可审计信号提取、三分类和无角色 reserve 分配；
- 将 v2 历史候选加入排除集合，避免把已观察项目包装成新样本；
- 对 repository、commit、tree、entry/doc blob 故障做项目级隔离。

## 阶段 3：零执行验证

- 运行协议校验、fixture 回归、故障注入和确定性分配测试；
- 对 `SketchyBar` 固定入口内容执行 regression audit；
- 验证 v1/v2 evidence inventory 未变化、0 Docker 和 0 credential/Provider 路径；
- 提交 implementation revision 后才允许冻结 execution authorization。

## 阶段 4：条件式唯一 catalog attempt

- 在用户授权、干净分支、create-once 路径和预算全部绑定后，执行唯一 source-only attempt；
- 审计 marker、报告哈希、inventory、分类计数和 12/12/12 reserve 配额；
- 失败则冻结结果并停止；通过则只进入 build + reference qualification 设计。

## 完成标准

- 新门禁能排除 v2 的决定性 macOS-only 反例并保留多平台 Linux 正例；
- 正式 attempt 若执行，得到按冻结门槛导出的单一决定；
- v1/v2 文件和 evidence 哈希不变；
- 不调用 Jev/Agent Provider，不创建动作矩阵，不实现 controller。
