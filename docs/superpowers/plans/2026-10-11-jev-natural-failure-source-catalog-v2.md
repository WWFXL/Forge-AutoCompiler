# Jev 自然失败 source catalog v2 实施计划

日期：2026-10-11。追踪：Issue #413。设计：
`docs/superpowers/specs/2026-10-11-jev-natural-failure-source-catalog-v2-design.md`。

## 阶段 1：冻结 source-only 协议

- 固定 GitHub 搜索条件、历史排除 revision、源码合同、分配算法、8/8/8 配额和停止规则。
- 创建 catalog manifest、Schema、预注册和 create-once evidence 路径。
- catalog 授权保持关闭，直到实现、测试和当前分支 revision 全部绑定。

## 阶段 2：实现与故障注入

- 实现 repository search、exact commit、root tree、入口 blob 扫描和确定性分配。
- 所有仓库级 API 操作返回结构化结果，不允许异常越过项目循环。
- 添加搜索全局失败、commit/tree/blob 超时、后续任务继续、网络原语和唯一分配回归。
- 验证 0 Docker、0 Provider 路径和 create-once 证据合同。

## 阶段 3：唯一 catalog attempt

- 在干净分支上完成 protocol validate 和 preflight。
- 单独提交 execution authorization，固定 implementation revision 和一次 formal attempt。
- 执行后立即审计 marker、报告哈希、inventory、项目计数和零 Provider 边界。
- 通过或失败均冻结原始 evidence，不重跑、不补样本。

## 阶段 4：条件式 build qualification

- catalog 失败：写只读结果分析，更新当前状态并停止自然失败 v2。
- catalog 通过：从 catalog 报告机械生成 24 项 source pool；在任何构建前冻结新的 build identity。
- 实现项目级 clone/命令超时隔离和网络失败识别，完成故障注入后再授权双 clean build。
- build 门槛失败则停止；通过后才设计 reference recipe、动作矩阵和 Provider 比较。

## 完成标准

- catalog 或 build qualification 得到按预注册门槛导出的关键决定；
- 所有正式 evidence、失败、超时和哈希可审计；
- 历史 evidence 未变化，cleanup 后无受管资源；
- 结论明确区分数据资格、基础设施和模型效果。

