# 简洁任务的两层经验与三系统接入结果

2026-11-04，Issue [#675](https://github.com/WWFXL/Forge-AutoCompiler/issues/675)。本阶段为工程接入与基础设施，解决最终论文核心组件未迁移到简洁任务的问题，**0真实Provider调用、0新增模型费，不新增方法效果分母**。旧E30/E33、E01及E35–E41和论文v0.6保持。

## 已完成

[核心边界与比较安排](2026-11-04-simple-build-core-boundary.md)固定本版保留模型规划、实际状态观察/Workflow、方案恢复、精确成功方案复用及跨项目一次经验注入。新增分类器、联网搜索、多Agent和产品UI迁移不作为本次论文比较前提。

- [两层经验适配](../../backend/packages/harness/deerflow/compile/simple_build_experience.py)：新可执行方案绑定完整公开任务，只有plan_id运行标签可不同；源码、镜像、平台、目标/澄清、并行资源必须匹配。只登记实际完整成功、原源码保持、重放/清理通过的最终命令，失败返回正常恢复。旧任务的产物路径/固定测试合同不冒充新任务精确命中。跨项目复用既有库及StateTargetBank排序/额度，改取简洁公开目标与已观察源码线索，恢复再使用当前真实失败；排除同项目族。
- [规划接点](../../backend/packages/harness/deerflow/compile/simple_build_task.py)：每次规划/新恢复任务开始检索一次并固定上下文；任务内读取工具或结构化输出不重新检索。私有参考仍不进入模型初始输入。
- [共享计量与强工具Agent](../../backend/packages/harness/deerflow/compile/simple_build_agents.py)：复用只读工具、上下文工作集、请求/响应/费用记录；工具Agent自己选择依赖/配置/编译/诊断指令和实际成功recipe，不接收Workflow阶段动作建议，不套全局阶段排序。提供与Workflow同等的保护原输入生成物reset，是否调用由Agent决定，实际动作进入重放。
- [统一研究入口](../../scripts/forge_simple_system.py)：基础Forge、经验Forge、强工具Agent共享公开任务、独立参考和结果字段；主构建接受后由外部执行交付、作者测试和原严格重放。作者测试设置共同CTEST_PARALLEL_LEVEL=1，已选参考无覆盖此设置的显式并行参数。CLI目前只接离线脚本模型；Provider需在独立授权协议下由外部注入，没有自动读取凭据或启动付费。
- [CXXCrafter参考适配](../../scripts/forge_simple_cxx_reference.py)：保留当前社区版原生Parser/Generator/Modifier/Judge，原生所有SDK轮注入相同公开任务并计量；固定镜像/资源/源码位置，私有测试不回送Modifier。用同一主组件识别、独立原测试及交付比较；重放关闭构建缓存，重新构建Dockerfile。代码/工具/宿主扫描与Forge仍不同，是完整系统参考，不冒充论文原版或纯状态消融。

## 实际工程运行

全部模型回复由离线脚本给出，但源码读取、Agent图、Shell、真实编译、作者测试和Docker重放均实际执行，不以手写方案的成功推断真实模型质量。

| 路径 | 观察 |
|---|---|
| jsoncpp/CMake、pigz/Make、libite/Autotools，各基础Forge/方案复用/强工具，共九条 | 主要构建、作者测试、交付、严格干净重放与cleanup均通过；三份同任务方案均跳过规划，0模拟模型调用 |
| pigz跨项目经验恢复 | 原make unknown-target真实失败；初始/新恢复分别检索一次；恢复任务内先读Makefile再交方案，沿用固定经验；修订后全部层级通过 |
| pigz强工具reset恢复 | 真实错target失败→显式生成物reset→正常make→提交实际成功recipe；全部层级通过 |
| pigz原源码改写负例 | 原pigz.c改写被拒，完整结果为false；原测试/交付/重放保持未观察，cleanup通过 |
| pigz CXX原生参考，最终独立v3 | 原生文档选择/生成/复核/两Judge共五个模拟模型请求；主构建、作者测试、精确交付内容与无缓存重建全部通过；两镜像及检查/构建容器已清理 |

pigz跨项目初始选择E04-slot-8/E04-slot-7，恢复选择E04-slot-7/E30-slot-14；两次检索对应两个Agent任务，三个模拟模型请求中恢复占两次。它证明任务内快照接线，不证明历史建议被模型采纳或带来增量收益。

**清理修复过程保留**：CXX首版v1的构建/测试/重放通过，但共用tag导致原镜像解绑后漏登记，原cleanup=true不能证明全部镜像清理；补充收据确认该镜像存在并精确删除。独立v2已清掉两镜像/容器，但Docker返回小写`no such object`被程序误判清理失败，原full=false保持；大小写兼容修复后的独立v3完整通过。三次不合为效果分母，不覆盖任何原失败或原件。

相关28项检查及改动文件Ruff/format通过；没有重跑本地产品全测或旧资格链，PR规定CI照常执行。已有pytest临时垃圾目录权限警告与本次结果分开，最终使用独立basetemp的相关检查通过。

## 证据与版本

[逐路径派生结果](../../benchmarks/analyses/simple-core-integration-v1/results.json)链接各原result及SHA。原件：

- `/home/yiwei/.codex/outputs/forge-simple-core-integration-2026-11-04-v1/`：九条跨构建系统正常路径。
- `/home/yiwei/.codex/outputs/forge-simple-core-extra-2026-11-04-v1/`：跨项目恢复与CXX v1。
- `/home/yiwei/.codex/outputs/forge-simple-core-final-2026-11-04-v1/`：强工具reset和原源码拒绝。
- `/home/yiwei/.codex/outputs/forge-simple-cxx-final-2026-11-04-v2/`：v1原镜像补充清理、v2原终态。
- `/home/yiwei/.codex/outputs/forge-simple-cxx-final-2026-11-04-v3/`：最终CXX路径及resource-check.json。

各组保存实际使用的driver、运行代码快照、公开任务/私有参考、原始请求/回复、源码读取、命令日志、结果和清理；九条及恢复路径的底座为#674合并39f28122上的工作树实现。运行时快照用于还原逐组代码，不用最终发布提交冒充早期运行revision。代码/CI/合并状态以#675关联PR及GitHub为准，只发布科研集成分支。

## 当前结论与下一步

核心组件已接入新研究入口，可以在固定版本上组织完整比较；本阶段不回答实际模型构建率、跨项目经验收益或相对CXX优劣。没有新增经验提炼、改写Harness代码或证明递归自进化。

下一项集中固定覆盖三构建系统的样本、独立主要组件/作者测试、公开任务、方法顺序和共享费用/时窗，正式采集基础Forge/经验Forge/强工具/CXX参考；同项目复用单独评价。具体48次仍是安排建议，不是本轮已冻结/授权的正式身份。旧模型效果按原任务使用，不因任务简化而作废，也不当作新版效果。原源码瞬时改写保护、已跟踪生成物重写和产品路径迁移等#673限制继续保留；不为“全部功能完善”无限推迟论文主比较。
