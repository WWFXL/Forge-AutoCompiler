# 按证据顺序规划的 Harness 更新提案（P5，待审核）

跟踪：[Issue #830](https://github.com/WWFXL/Forge-AutoCompiler/issues/830)。阶段：方案设计与实验准备；0 Provider，不是新效果结果。用户本轮授权只覆盖版本整理与提案准备，未接入运行入口、未启动真实比较、未修改论文。

## 问题与依据

[E60统一基座比较](2026-11-17-unified-base-harness-comparison-results.md)中，LH_v1初始规划113次请求、原组59次；前期费用增加超过恢复节省。libtasn1更新组规划20次，选择当前gnulib后出现补丁不匹配；原组取得项目绑定版本后完成。libffi则保留了依赖经验引导更短恢复路径的局部收益。因此本次保留当前工具与恢复能力，优化初始规划的证据获取和停止方式。

当前SIMPLE_PROMPT已要求先用README和根构建文件、证据足够即提交，PLANNING_DEPENDENCY_PROMPT也已要求定向依赖查询。本候选把这些原则细化成按构建系统选择入口、依赖版本优先级、补查触发条件和明确收敛条件；不是首次引入README阅读或依赖检查，也不声称既有轨迹已经证明该候选有效。

dsvpn/zstd不完整工具参数的底层原因仍待定位。本提案不调整输出schema、解析链路或结构纠正次数，不将读取流程改进当作该问题已解决。相应排查另行开展；如形成共同修复，后续两组使用相同修复版本。

## 优化前后版本与比较边界

源代码参考revision：`1de5fcf6ebf9334f4cbf8d7b228e820aa794c486`。

| 项目 | 优化前 | 本次候选 |
| --- | --- | --- |
| 名称 | 当前LH_v1中的P0规划 | 当前LH_v1中的P5_evidence_order规划 |
| 规划Harness | P0，无额外planning_guidance | P0追加下文的证据顺序指导 |
| 规划工具 | 现有只读源码、依赖与环境查询 | 相同 |
| 恢复Agent | 当前LH_v1的R2及已审核指导/诊断能力 | 相同 |
| 模型、Workflow、上下文管理、文件政策、验收 | 当前共同基座 | 相同 |
| 成功方案复用／动态经验检索 | 后续比较均关闭 | 相同 |
| 项目特定答案／新增CCScanner | 无 | 无 |

这里的优化前是当前LH_v1，不是E60中的LH_v0_common。不能直接拿历史LH_v0_common对新候选归因读取流程收益。正式比较需在同一代码版本、同一项目上运行共同基线，仅切换planning_guidance。

提示词追加位置遵循现有propose_simple：SIMPLE_PROMPT → PlanningHarness追加指导 → SOURCE_REVIEW_GUIDANCE → PLANNING_DEPENDENCY_PROMPT。恢复调用不应用PlanningHarness的指导；恢复原有附加提示保持。任务/source_packet、工具schema和工具历史仍是独立输入，不把它们混称为系统提示词。

## 完整新增指导（审核正文）

```text
按以下证据顺序完成初始规划。顺序用于减少无目标探索，不要求机械增加工具调用。
1. 构建说明：先利用source_packet与已有工具对话中的材料，定位README、INSTALL或其明确链接的构建章节，确认作者推荐的Linux普通构建方式和主要程序/库。只补读缺少的相关片段；已有证据不重复读。文档不存在或无构建说明时，直接查实际构建入口，并在reason简要注明依据。
2. 构建入口：沿作者推荐入口检查直接相关的构建声明。CMake看根CMakeLists.txt以及影响主构建的相关cmake文件/预设；Autotools看configure.ac或configure.in、Makefile.am及实际使用的autogen/bootstrap；Make看Makefile或GNUmakefile及必要include；Meson看meson.build、必要选项与子项目声明。按实际检测到的系统选择，不逐一搜索所有系统；不要把尚未生成的Makefile当成必需输入。多构建系统并存时优先作者推荐的普通Linux入口，不为比较入口而展开探索。
3. 必要依赖：从上述说明和脚本提取当前主要构建真正需要的工具、开发库、配置生成宏和外部源码。仅对有明确线索、且是否满足会改变方案的依赖调用现有环境查询；可将多个明确候选合并查询。依赖版本有约束时优先查项目声明、锁定信息或子模块指针，不直接选最新版，也不凭空降级。区分缺包、搜索路径与版本问题。不要为可选示例/完整测试遍历依赖，也不要为所有include逐项查包。
4. 形成方案：把已确认缺失的必要依赖写为dependency动作，安装由Workflow执行；保留生成配置文件的必要步骤，再给主项目configure/build指令。Make直接构建有依据时无需configure。每步标注实际文件或查询证据source，显式保留所需版本、工作目录、安装前缀和环境变量；各Shell不继承状态。规划时不执行安装或试编译，不扩大任务目标。
5. 收敛：主要目标、构建入口、必要准备和配置/编译命令已有依据，且没有会改变方案的具体未解问题时，立即提交完整SimpleBuildActions。允许把无法事前判断的问题交给执行反馈与恢复，不继续排除所有潜在错误。需要补查时，先明确一个具体疑点，只读能解决它的相关文件/查询；无新增证据不重复相同读取或查询。文档与脚本矛盾时按实际入口做定向核实，无法确定则说明阻塞，不猜测已满足。
reason简要说明构建入口及关键依赖判断即可；无需逐项写检查报告，不增加输出字段，不在reason中塞命令列表。始终使用既有结构化输出契约。
```

这是提示词组织的默认路径，不是新编码的强制状态机。source_packet已有材料可直接满足检查；无README允许读实际入口。允许为具体疑点回查，不按固定调用次数机械执行。Meson条目仅覆盖规划读取，不代表本轮验证或新增了Meson端到端支持。

## 前后完整提示与逐行差异

- [修改前完整规划系统提示文本](../../benchmarks/fixtures/planning-evidence-order-v1/planning-before.txt)
- [修改后完整规划系统提示文本](../../benchmarks/fixtures/planning-evidence-order-v1/planning-after.txt)
- [逐行差异](../../benchmarks/fixtures/planning-evidence-order-v1/planning.diff)
- [可装配候选](../../benchmarks/fixtures/planning-evidence-order-v1/candidate.json)与[版本指纹/零费用核对](../../benchmarks/fixtures/planning-evidence-order-v1/review-metadata.json)

以上完整提示指无动态经验注入、开启当前规划依赖查询时传给create_agent的system_prompt文本；不包括模型工具schema、动态任务或之后的工具对话。候选只是待审文件，未修改SIMPLE_PROMPT、PLANNING_DEPENDENCY_PROMPT和任何历史候选/manifest。

## 审核后如何评价

审核后再接入现有PlanningHarness接口，并用少量不同构建系统项目观察：是否优先使用已有文档、读取实际入口；是否仅针对明确依赖查询；已有依据时是否提交。轨迹同时保留合理的额外检查，不把多调用一律判成无效。

正式比较优先选新项目并隔离历史优化轨迹的仓库族，两组同任务/源码/环境，各自从零规划。项目清单、样本数、预算及时窗尚未确定，本文件不是正式预注册或付费授权。主要报告全项目完成率、费用与时间；辅以初始/恢复请求、重复读取、依赖遗漏和输出失败，分析前期调查是否被后期恢复节省抵消。若样本出现输出失败，按实际失败报告，不能剔除或回填。

当前完成标准是候选可审核、可由现有接口装配、恢复提示不受影响；不以本地检查代替模型遵循率或构建效果。结果仍须先交用户审核，获得同意后入论文。

## 本轮实际核对

候选经现有PlanningHarness加载、落盘重读和实际提示装配检查通过，新增指导2728 UTF-8字节，低于既有6000字节上限；恢复路径返回共同原提示。现有`test_update_binds_evidence_and_changes_only_initial_prompt`实跑通过（1 passed，6 deselected），`git diff --check`通过。仅新增待审材料及状态记录，没有改运行代码、工具或实验协议，也没有运行模型或真实构建。
