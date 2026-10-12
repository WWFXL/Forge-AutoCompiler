# Linux 构建闭合资格 v5 实施计划

日期：2026-10-12。追踪：Issue #417。设计：
`docs/superpowers/specs/2026-10-12-linux-build-closure-qualification-v5-design.md`。

执行状态：阶段 1-4 已完成。机制 canary 通过，下一项独立工作是设计 formal build/reference qualification
identity；本计划不授权或执行该正式 identity。

## 阶段 1：纯函数资格核心

- 新增独立 v5 runner，不修改冻结 v1-v4 runner；
- 复用 Forge `_classify_compiled_artifact` 作为 ELF/`ar` 结构裁判；
- 实现 ELF/archive machine 提取、文件增量快照、动态 target signal 和单次/双次分类；
- 用真实 gcc/ar 产物以及合成 PE/Mach-O、foreign ELF、freestanding/cross-target 日志验证分类优先级。

完成标准：聚焦单元测试覆盖 host closure、non-host、no artifact、stable failure candidate、网络、timeout 和不一致
结果；Ruff 通过。

## 阶段 2：隔离 Docker observation

- 从 exact commit clone 到只属于本次 canary 的工作根；
- 使用冻结 `autocompiler:gcc13`、`--network none` 和固定 timeout 运行默认路径；
- 每个 case 使用全新 workspace，保存结构化结果与日志哈希；
- 无论成功、失败或 timeout 都清理受管容器。

完成标准：本地合成 CMake、Make、Autotools fixture 均能产生稳定宿主闭合；合成 cross/freestanding fixture 被稳定
排除；cleanup 为真。

## 阶段 3：已暴露真实项目机制 canary

- 输入仅使用 v2/v4 已冻结 exact commit，不做新搜索，不分配正式实验角色；
- 验证 `SketchyBar` 和 v4 构造效度审计中的 Linux 正例、非宿主反例、header-only 风险；
- 允许 Linux 项目因依赖缺失成为 `stable_failure_candidate`，但不得因旧 source 标签直接排除；
- 允许信息不足的非宿主项目保守进入 `target_unresolved`，但不得成为 `qualified_natural_failure`。

完成标准：所有已审计反例均无法进入自然失败角色；至少一个 Linux 用户态真实项目形成动态宿主闭合；旧的两个
source false positive 均进入动态观察。

## 阶段 4：冻结结论与下一决策

- 将机制 canary 与测试结果写入版本化 report；
- 更新 `RESEARCH_STATUS.md` 和 `.claude/memory/project.md`；
- 若机制资格通过，下一阶段才设计全量 build/reference formal identity、reference recipe 审核和角色分配；
- 若机制失败，停止扩展候选池，保留 canary 负结果并重新设计 target observation。

本计划全程 0 credential、0 Provider、0 model token。v1-v4 frozen evidence 保持只读。
