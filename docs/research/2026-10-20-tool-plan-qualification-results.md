# 工具初始方案零Provider资格结果（#540）

工具生成的三个候选均通过原严格闭环：buffer/Make、uncrustify/CMake、libverto/Autotools，3/3 strict，0未观察、0模型请求/Token/费用、12条Shell。**这证明在这三个已见开发任务和固定镜像上，初始方案可以由工具生成，无须先请求模型；不证明整体策略成功率、费用或时间优于模型规划。**

## 问题与实现

#538的方案方法初始规划占费用约88%，且请求减少没有转化为整体费用优势。本轮按用户要求，先静态核对CXXCrafter公开社区版固定commit与CompileAgent论文第4–5页，再用已有PlanTask/BuildPlan和Workflow完成最小零模型资格。

来源与差异见[工具核验记录](2026-10-20-tool-plan-tools-review.md)。CXXCrafter社区版存在文件名/浅层入口提取和环境探测，文档选择、总结与Dockerfile生成仍使用模型；CompileAgent的File Navigator和Instruction Extractor内部也是模型Agent，不能将它们误算作零费用静态工具。CompileAgent本轮未定位到作者确认的公开实现，描述限论文，不冒用同名产品。

新模块仅使用源码根入口与固定任务，不接收正确参考、历史成功方案或项目名称分支：CMake为标准配置/构建模板、Make为默认目标、Autotools从已有configure或autoreconf开始。固定测试由系统逐字段装入，不改Shell引号和测试内容。交付basename来自任务，执行后在候选构建目录中找唯一ELF/ar普通文件，作为可重放artifact_stage；严格结构、来源、完整测试、精确交付和clean replay裁判保持。

这种资格仍以作者提供的交付目标和完整验证为前提，不是自动定义测试或发现正确任务。自定义构建根、多入口、已有同名文件、特殊配置和依赖解析仍有覆盖边界；生成收据显式保留依赖/默认配置/交付唯一性三个未决问题。

## 实际观察

| 项目 | 系统 | 生成候选耗时秒 | 总臂耗时秒 | Shell | 原完整测试及重放 | 严格终点 |
| --- | --- | --- | --- | --- | --- | --- |
| buffer | Make | 0.002663 | 9.064 | 3 | 原Makefile完整自测，原工作区和重放均有✓/ok | 通过 |
| uncrustify | CMake | 0.021600 | 579.488 | 4 | 原工作区与重放均14/14 CTest | 通过 |
| libverto | Autotools | 0.003239 | 32.217 | 5 | 原工作区与重放均六测试6/6、0skip、0fail | 通过 |

生成耗时只计源码检查和候选渲染；解包、全源码hash、运行、测试、交付、replay和cleanup在总臂时间内，不将生成毫秒数当作整个构建耗时。uncrustify首轮完整测试250.415秒，完整重放也执行同一测试，没有过滤用例或缩短范围。总臂时间约620.769秒，不能与旧身份/模型结果做未经控制的速度因果比较。

三个原源码树均未改变，三个独立clean replay均通过完整交付集合、类型、大小、SHA-256及执行验证；原编译和重放容器实际均不存在。libverto本轮从新干净源码按默认配置完整构建，不是#530“旧工作区仅改configure启用shared”的恢复反事实，不能回填旧负结果，也不能据此主张旧失败已被修复。

本轮没有发生实际失败或Agent恢复；多入口/不支持/同名产物拒绝、真实ELF暂存、缺失/多匹配暂存拒绝、恢复前保存交接与零模型门禁由19项新单元测试验证。失败分支尚无本轮新Docker观察，不能声称自然覆盖率或恢复成功。原#536接管资格与旧失败证据保持各自身份。

## 固定身份、版本与证据

- 身份：`cpp-build-tool-plan-qualification-v1`；Issue #540、PR #541，运行release `7611a4c5cd50cbb1ab7539e9b00b2250ac361862`。固定开发顺序buffer/uncrustify/libverto，一次生成和执行，全部已见，不称holdout。
- 协议：`benchmarks/manifests/cpp-build-tool-plan-qualification-v1.json`与同名preregistration，冻结93组件。2CPU、节点1200秒、32命令，单命令600秒、evaluator/replay900秒、cleanup120秒。两小时工程上界自本协议准备时冻结，零Provider，不继承或延长旧付费授权。
- raw：`/home/yiwei/.codex/outputs/forge-tool-plan-qualification-v1/`；28272普通文件、6链接、128172729 bytes，inventory SHA-256 `692cab463a48a263b8e3724f895b1ad92f668415f4a8d4eac7b1322d10d6bc5f`。原result的kind沿用旧执行器标签，根身份与新聚合明确为零Provider工具资格，不能将继承标签解释为真实模型调用。
- 独立审计：`/home/yiwei/.codex/outputs/forge-tool-plan-session-2026-10-20/independent-audit.json`，valid=true。纯stdlib脚本不导入生成器/执行器，复算inventory/93快照/原任务/方案fingerprint/固定验证/原源码/完整测试日志/交付与replay哈希/实际容器不存在/零模型用量。实现SHA-256 `4169a45e9b51ad9388e58cb687a4e2b5ce27778970e48e6f9e9bff2c7195bd3c`。
- 同一会话输出目录保存`related-work-receipt.json`及公开代码节选、`full-test-summaries.json`、`local-checks.json`与运行日志。未复制个人Vault、未将知识库或人工正确参考注入执行上下文。
- 本地19项新测试、完整产品2052 passed/44 skipped/27 warnings，Ruff与538文件格式检查通过。历史pytest临时目录root权限清理告警保留，不计作科研失败。最终head CI/PR合并/Issue状态以GitHub和同目录`final-publication-audit.json`为准；仅合入依赖分支`yiwei/534-rq3-natural-failures`，不进main，不提交用户HTML。

## 下一决定

该结果支持把“工具初始方案＋Workflow＋失败Agent”保留为下一次比较的候选，并继续主线。当前最便宜的下一项是固定共享测试装配与恢复接口、登记模板覆盖与未覆盖情况，再冻结真实比较；不能把当前3/3与旧模型9/12作直接优劣比较。

公平比较应让模型方案与工具方案共用相同固定测试装配、Workflow、恢复Agent、状态材料和验收，同时完整计量工具探测/渲染/失败/恢复与模型读取/输出。即便如此，与强工具Agent仍是完整策略比较，不能声称只隔离了纯规划变量。工具方案本轮改变了方案来源和系统装配接口，尚未隔离这两个因素。

不加P2、不改RQ3原分母、不降低严格裁判，不将命令模板当作通用机制创新。本轮不新增付费比较；后续Provider阶段须先冻结身份并核验新的有效授权、预算与停止规则。
