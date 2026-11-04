# 简洁构建任务最小实现与真实工程试运行

2026-11-04，[Issue #673](https://github.com/WWFXL/Forge-AutoCompiler/issues/673)，承接[#671方法设计](2026-11-04-simple-build-task-design.md)。**工程修复与基础设施阶段，0 Provider调用、0模型费，不是新系统比较或模型效果实验。** 旧E40/E41、论文v0.6及其分母保持。

## 已实现的运行路线

`PublicBuildTask → 规划/方案恢复接点 → SimpleBuildPlan → 原Workflow执行/修订 → 实际配置观察 → 独立主组件检查 → 冻结主要构建结果 → 精确交付、作者测试、原严格clean replay → cleanup`。

- [任务与规划接口](../../backend/packages/harness/deerflow/compile/simple_build_task.py)明确`simple-build-v1`。公开任务只含源码/环境身份、简洁目标和共同澄清；`BuildReference`另存声明式主要组件及作者测试。初始提示不含参考成功命令、精确产物路径或逐项目测试脚本。规划仍使用只读工具、原计量middleware和结构化动作；在middleware实际替换请求的位置也过滤私有评测字段，脚本模型的真实Agent图已验证该边界。本轮没有验证真实模型的方案质量。
- 新`SimpleBuildPlan`仅含依赖、配置、编译；独立定义而非给旧`BuildPlan`塞空smoke/stage。旧入口不迁移。原Workflow仅增加方案模型和步骤校验的覆写接点，原默认装配、角色判断和验收不变。
- 模型`stdout_contains/files_exist/directories_exist`保留在建议原件中，装配时不转成执行否决条件。CMake从实际Cache取得generator、源码与构建目录，检查对应Makefile或Ninja入口；没有指定Ninja时不强求`build.ninja`。Make不凭空增加configure。Autotools实际configure后观察`config.status`与Makefile，不声称已理解全部目标语义。
- [实际观察与运行层](../../backend/packages/harness/deerflow/compile/simple_build_runtime.py)按独立组件的精确规范名/版本化别名定位新产物，复用原ELF/ar结构检查，加`readelf`平台核对；排除源码内既有预编译物及其字节副本、越界链接和系统路径。当前使用安全目录扫描，没有实现CMake File API。只定位路径不会改变已成功动作或重新编译。
- 恢复仍返回完整方案；原首变化后缀算法保留。依赖/配置变化时插入显式生成物reset，保留原输入集合、物理删除新增文件后重做配置/构建，reset也进入成功配方。无变化建议仍拒绝。正常`make clean && make`或`make distclean`后配置可作为同阶段前置，其他混合阶段、任意rm和关闭严格Shell继续拒绝；不按项目名称分支。
- `primary-result.json`首次通过后独立保存。交付、作者测试、clean replay和完整完成分别记录，未知不填通过；测试有单独时限，不消耗主构建恢复预算。记录配置/构建、恢复执行、产物定位、交付、测试、重放和总耗时。产品Session的verified/completed不作为本新任务的完整成功字段。

## 实际运行结果

原归档只读复用指定commit，镜像固定`sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`，2并行；主Workflow600秒、单命令180秒、作者测试90秒、replay240秒。全部方案和恢复回复由工程脚本提供，**没有模型探索或效果分母**。未自动重试旧实验。

| 工程路径 | 实际观察与恢复 | 主构建/交付/干净构建重放 | 独立作者测试 | 新任务完整完成 |
|---|---|---|---|---|
| jsoncpp，正常 | 默认Unix Makefiles；故意保留错误Ninja/产物路径/配置日志候选，未否决实际主库 | 均通过 | 并行CTest 2/3通过，1失败 | 否 |
| jsoncpp，恢复 | 错target真实失败；方案改为Ninja，实际reset后配置和构建 | 均通过 | 并行CTest 1/3通过，2失败 | 否 |
| pigz，正常 | 默认make；没有configure | 均通过 | 原make test通过 | 是 |
| pigz，恢复 | 错target真实失败；make clean与make同阶段执行 | 均通过 | 原make test通过 | 是 |
| libite，正常 | 原autogen生成辅助文件，configure后make | 均通过 | 原21测试通过 | 是 |
| libite，恢复 | 漏bootstrap导致configure不存在；保留127，补原autogen后恢复 | 均通过 | 原21测试通过 | 是 |

六条主构建/交付/构建replay/cleanup均通过；原作者测试与完整完成各4/6。jsoncpp测试失败时仅成功构建配方参与该次replay，不将其写成全部作者测试重放通过；完整完成仍否。所有受控失败和其后修订均保存，没有用恢复成功覆盖原失败。

**独立串行测试检查**：原运行的CTest继承2并行，`jsoncpp_readerwriter`与`jsoncpp_readerwriter_json_checker`处理重叠数据，后者日志分别出现4和3个数据项差异。独立新目录使用`ctest -j1`，正常/恢复两条均主构建、作者测试、测试重放、交付及cleanup通过。观察与并行冲突解释一致，但未逐数据项追踪根因；不把它宣称为库算法缺陷已修复，也不改写原两次失败。正式比较应在各方法共同测试资源中明确串行设置。

## 证据与复现

- [派生结果JSON](../../benchmarks/analyses/simple-build-implementation-v1/results.json)逐条链接原记录和失败日志，不合并两批分母。
- 原六条：`/home/yiwei/.codex/outputs/forge-simple-build-implementation-2026-11-04/`。
- 独立串行两条：`/home/yiwei/.codex/outputs/forge-simple-build-serial-tests-2026-11-04/`。
- 各目录保存`scope.json`、实际初始/恢复上下文、Session命令/完整日志、方案版本/交接、`primary-result.json`、`postcheck-result.json`、结果与cleanup。`runtime-snapshot-v1/v2`保存对应未提交工作树代码及SHA，不用最终发布HEAD冒充当时运行版本。原归档/commit及参考组件依据在scope中。
- [零Provider CLI](../../scripts/forge_build_simple_task.py)的`--help`列出独立task/reference/actions/repair-actions/source-archive/output-root输入。输出目录必须新建；退出0仅表示主要构建与cleanup成功，进一步验收看分层字段，不能用退出码推断全部测试通过。

相关59项检查和改动文件Ruff通过，含真实本机静态库构建、错目标恢复、物理清理、错误候选断言、预编译副本排除、源码改写拒绝、真实Agent图的公开输入过滤及原Workflow回归。Docker实跑证明最小路线可执行；检查数量不作为科研工作量或效果。全仓格式检查另发现既有`tests/test_recovery_ablation.py`缺一空行，同一问题在HEAD原文复现；本轮未格式化无关文件。CI与实际合并以对应PR记录为准，不重跑本地产品全测或旧资格链。

## 限制与下一项

当前是独立研究入口，未切换产品默认路径或迁移旧ProjectRecipe，尚未将强工具Agent/CXXCrafter接到新任务。新模型比较的样本、统一测试/replay资源、总费用及有效时窗未冻结。

本版保护原文件/链接的内容和文件身份，命令前后核对；不宣称覆盖所有瞬时写入事件。原文件中已跟踪的生成物仍不能随意重写，需要已有审阅生成规则的独立接入；本次libite正常生成的是新增文件，不能据此声称任意Autotools仓库均支持。主组件参考仍须事前少量人工核对；扫描与工具观察是有界实现，不是完整依赖/目标语义解析器。支持范围暂为Linux x86_64/aarch64 ELF/ar，实际Docker仅测x86_64。

下一项以这个入口接入Forge与强工具Agent的共同简洁目标和结果检查，固定同模型、环境、预算、无经验条件及独立测试资源，然后做完整比较；CXXCrafter按实际适配差异作参照。后补同目标状态/经验消融。本轮不启动付费、不增加效果实验编号，不把任务工作量简化当算法加速，也不因旧实验目标更复杂而作废旧论文结果。
