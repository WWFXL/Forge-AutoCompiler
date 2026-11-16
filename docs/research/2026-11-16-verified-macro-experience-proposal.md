# 已验证宏依赖经验：恢复Harness待审提案

2026-11-16；Issue #791。类型：已有结果分析与提示词提案准备，0新增Provider、0新构建，不是效果实验。本轮完成经验整理和提示词差异，待用户审核后再接入及观察。

## 为什么修改

上一自主观察已经把候选送达Agent，Agent仍从本地缺宏错误推断版本移除。当前通用原则告诉它“应当核实候选”，但没有提供该宏与真实开发文件的已知关联。本提案把已验证关联作为显式经验加入恢复指导，使下一动作有具体依据。

这不是“模型缺少预训练知识”的已证结论；它是依据已观察错误行为提出的Harness改进假设。

## 经验卡：缺失宏与提供包

| 项目 | 已有依据 |
|---|---|
| 触发现象 | Autotools日志：`possibly undefined macro: LT_SYS_SYMBOL_USCORE` |
| 适用条件 | 当前缺口确为此宏，使用Libtool/ltdl宏的配置生成流程；Debian/Ubuntu包名为候选线索 |
| 已验证环境 | 当前Ubuntu镜像，libtool及libltdl-dev均为`2.4.7-7build1`；其他发行版/版本尚未验证 |
| 提供关系 | `libltdl-dev:amd64`提供`/usr/share/aclocal/ltdl.m4`，第757行有`AC_DEFUN([LT_SYS_SYMBOL_USCORE],` |
| 原因分支 | 宏提供包未安装；或已安装但宏文件目录未被aclocal发现。不能由局部无定义直接推版本删除 |
| 核实方式 | 既有`diagnose_dependency`查询候选描述、安装状态、已安装文件及搜索路径；必要时`package_file_search`查询`ltdl.m4`提供包 |
| 补救措施 | 缺包时在dependency步骤用APT安装`libltdl-dev`；已装时核实文件/搜索路径，只在实际路径缺失时补入作者流程 |
| 继续位置 | 重新执行原配置生成，再配置、构建；不消费失败遗留configure，不固定检测值替代真实宏 |
| 可复用范围 | 相同缺口与相应环境，可跨项目触发；不能扩大成全部LT_宏或全部Autotools错误 |

原证据是#754真实工程构建中的命令`command_9ed72e3fc06b487e971d6cb29cbe901e`，退出0，输出同时记录包版本、文件归属及宏定义。原件日志：

`/home/yiwei/.codex/outputs/forge-libffi-recovery-assembly-repair-2026-11-16-v1/libffi/.compile-sessions/simple-system/1f47c2499295/logs/command_9ed72e3fc06b487e971d6cb29cbe901e.log`

[原构建报告](2026-11-16-libffi-recovery-assembly-repair.md)记录补包后原生成/配置/主构建、交付及干净重建通过，没有降级或替代宏。[查询工具修复](2026-11-16-dependency-provider-repair.md)与[诊断流程工程验证](2026-11-16-dependency-diagnosis-selection.md)提供后续索引/查询能力依据。[最近自主观察](2026-11-16-libffi-dependency-diagnosis-results.md)则记录候选持续送达、核实为空的实际缺口。全部复用旧原件，未重新运行资格或构建。

## 提示词改动

候选名`R2_verified_macro_experience_v1`。相对最近实际使用的`R2_dependency_diagnostic_order_v1`只追加一条782字节经验；完整恢复指导5016→5800字节，处于现有6000字节边界内。不删除或改写原R2/通用诊断指导，不更改工具和Workflow。

新增原文：

> 已验证错误经验（按错误与环境适用，不按项目名）：
> 若Autotools报LT_SYS_SYMBOL_USCORE未定义，先核实ltdl宏提供者。已验证Ubuntu包libltdl-dev 2.4.7-7build1提供/usr/share/aclocal/ltdl.m4及该宏；仅装libtool可能缺它，不能推断新版删宏。
> 在Debian/Ubuntu先用diagnose_dependency(kind="macro", item="LT_SYS_SYMBOL_USCORE", candidate="libltdl-dev")核实包/安装/路径，必要时以package_file_search查ltdl.m4。缺包则在修订dependency步骤安装：apt-get install -y --no-install-recommends libltdl-dev；已装则核实宏文件及aclocal搜索路径。修复后重跑原配置生成、配置和构建。其他发行版先查提供包；不把全部未定义宏套用此包，不用固定检测值替代真实宏。

这里主动向Agent提供已验证包名与文件名，与上次“无答案自主诊断”条件不同。后续效果应解释为经验辅助的动作选择，不能当从零发现提供关系。libffi也是经验来源项目，仅能先观察利用能力；跨项目效果须另取项目验证。

## 接入位置与保持项

审核后拟由独立观察入口将候选作为`recovery_harness`传入现有执行链。现有`simple_build_task.py`只在真实恢复阶段应用该对象；因此初始规划不会收到这条经验。固定一条经验直接加入恢复系统提示即可，无需新检索器、skill执行器或Agent。

当前只保存候选文件，没有修改运行入口或默认行为。恢复环境、诊断自动查询、诊断记录及其追加提示原样保留。动作仍由Agent提交完整方案，Workflow执行；预算/查询额度和主要结果验收不变。候选来自版本化科研材料，不从个人知识库动态注入。

## 本轮完成与下一步

已通过实际`RecoveryHarness`结构校验、底座指纹及提示词装配，验证唯一文本差异为追加经验，长度5800字节；没有新增模型请求或构建。材料检查仅证明提案可装配，尚无模型采用或效率效果。

请用户审核本条经验和提示词差异。审核后再实现单次观察入口、绑定新运行身份和有效费用/时窗；先看是否采用真实依赖、不再生成替代宏，以及构建/交付/重建和全部开销。后续迁移候选按同类自然缺口选取，若只能受控构造则单独说明。

材料目录：[新增指导](../../benchmarks/fixtures/verified-macro-recovery-experience-v1/experience-guidance.md)、[当前组合](../../benchmarks/fixtures/verified-macro-recovery-experience-v1/baseline.json)、[候选组合](../../benchmarks/fixtures/verified-macro-recovery-experience-v1/candidate.json)、[完整提示差异](../../benchmarks/fixtures/verified-macro-recovery-experience-v1/prompt.diff)、[材料核验](../../benchmarks/fixtures/verified-macro-recovery-experience-v1/material-check.json)。候选指纹`9de184d72f39866fd832a985f720293d6432ccd7c8a033e94f81f2376d4836d8`。不修改论文、旧结果或独立项目分母。
