# 恢复Harness离线提案：等待用户审核

本阶段为历史结果分析与必要基础设施，Issue #709。已取得一次真实高级模型提案，尚未执行任何候选比较，未改动论文。本报告是待审方案，不能当作效果结论。

## 研究问题与变量

在固定初始规划H0、Flash构建模型及共同修复底座的条件下，恢复指导能否改善失败证据使用，减少重复探索与恢复长尾，同时保持主要构建及可复现交付？前两轮只改初始规划，本轮候选只追加恢复指导；不能把跨轮差值当作恢复优化效果。

H0恢复使用现有SIMPLE_PROMPT；候选暂称R1（代码名H_R_candidate），在相同提示后追加高级模型的原文。它不是H2初始策略与恢复策略的混合版本。工具、状态路由、Workflow、预算及独立验证不随候选变化。原有成功dependency保留、显式轻量验证等共同修复由两组共享，不计R1贡献。

## 来源材料与实际提炼

材料包括E50/E52全部可定位自然恢复：double-conversion四次、check三次、libsigcplusplus五次，共12次恢复调用，来源为7个既有构建槽和3个项目；另取yaml-cpp、libhydrogen、libsodium三条正常成功作为行为边界，总15条材料。来源不是新增效果样本。

输入保存真实公开任务、失败handoff、可见工具反馈、最终动作及整槽结果；每次最多保留前四/后四工具反馈，保留省略计数、全部工具参数频次及来源哈希，显式区分整槽结局和单次恢复成败。未读取隐藏推理、私有参考或个人知识库；下一轮18个评价候选不送入优化器。

一次请求使用RichLab gpt-6-astra路由，响应标识gpt-5.6，按用户接受的披露，不能证明实际后端为Astra。输入103,189、输出2,667，合计105,856 Token，按输入/输出各1美元每百万Token估算 **0.105856美元**，耗时51.89秒。无自动重试、未知用量0。

## 高级模型提出的五项诊断

| 实际问题 | 建议行为 |
| --- | --- |
| 1. 真实失败已指向文档生成工具缺失，但恢复仍多次重读README、顶层构建文件和配置文件的无关区段。关键证据其实只需确认失败目标是否可选、是否存在作者配置开关、关闭后主库和默认非文档组件是否仍保留。 | 收到构建失败后，先从交接尾部提取首个确定失败目标、缺失命令或错误文件，再只补读定义该目标的局部构建文件、对应配置选项及顶层目标关系。若这些材料已证明故障限于可选组件且主组件不受影响，立即提交修订；同一文件仅在前次片段未覆盖所需定义或日志出现新故障时续读。 |
| 2. 依赖下载连续超时时，曾尝试读取越界日志并转向替代构建入口；替代方案起初又显式限定单一产物，缩小了该入口的自然默认构建范围。失败交接已经包含下载停滞位置和重复超时，越界读取没有新增证据。 | 优先使用交接中的退出码、日志摘要和哈希判断失败是否重复；摘要已完整显示同一下载阶段停滞时，不再读取相同日志。只有需要区分网络、解析、安装或后置验证失败且摘要不足时才读取规范日志路径。切换作者支持的备用入口前，局部读取其默认目标定义，并保持该入口自然包含的主组件；除非任务或作者说明明确要求，不显式收窄到单一库或产物。 |
| 3. 缺失命令已由失败日志明确定位，作者说明和启动脚本也直接给出该工具为源码检出构建的必要依赖；部分轨迹仍遍历多个构建系统、生成文件目录和大量子目录，才回到同一依赖结论。 | 对“command not found”类配置失败，按最短证据链处理：失败命令所在脚本、作者依赖说明、主构建入口。三者一致时直接新增必要依赖并保留原配置与构建步骤。仅当依赖不可安装、作者入口不一致或缺失命令可能属于可选组件时，再比较备用入口和组件开关。 |
| 4. 容器内补装依赖后主构建可完成，但另一轨迹的干净重放仍失败；后续修订只展示配置和构建步骤，说明容器成功不能替代从零配方完整性。现有执行器已会保留成功依赖，因此不应把该人工修复包装成新的自动能力。 | 恢复提交前检查当前完整方案是否仍引用所有已成功且从零构建必需的dependency step_id；不要因当前容器已有工具而省略。只有证据证明依赖不再需要或被新步骤完整替代时，才使用discard_dependencies并写明原ID和理由。对于尚未启动的重放，不推断失败；对于已有失败结果，原样保留。 |
| 5. 文档依赖故障存在两种均曾完成主任务的恢复：安装文档工具，或使用作者提供的文档开关。仅凭单条成功轨迹不能宣称某一种普遍更优；选择必须结合组件是否可选、安装可行性、默认范围及任务要求。 | 遇到文档、示例或测试辅助目标失败时，先分类：若任务要求或作者普通默认构建不可分割地包含该组件，补齐依赖；若作者明确标为可选并提供配置开关，且关闭后主库、主要程序及其他默认必要组件仍保留，可采用该开关。reason中写明分类证据和保留范围，不把一次成功外推为通用规则。 |

上表为模型提案，预期行为尚未经比较验证。特别是依赖保留已由共同执行器保障，候选对它的重申不能再次算作新增机制；本轮真正待检验的是恢复中的证据选择、动作取舍和收敛。

## 待审核的完整新增指导（模型原文）

```text
恢复先以最近失败交接为索引：记录失败阶段、退出码、首个确定错误、已成功步骤和当前目标范围。交接摘要足以定位时直接处理；仅补读回答当前决策所需的局部证据，通常是失败规则、对应配置选项、顶层目标关系或缺失命令所在脚本。不要预先遍历全部文档、备用构建系统、示例和测试，也不要重复读取内容未变化且已覆盖问题的片段；日志摘要被截断、错误归属不明或后续日志出现新故障时允许再次读取。

动作按证据强度选择：明确缺失的必要工具或库优先补依赖；配置冲突修正作者支持的选项或构建目录；只有当前入口持续受真实环境约束且作者明确支持备用入口时才切换。切换入口前确认其默认目标范围，不显式缩成单一产物。可选组件故障可使用作者开关，但必须证明其可选性以及主库、主要程序和其他必要组件仍在构建图中；否则补齐依赖。

提交完整方案时保留仍适用的成功前缀和成功dependency step_id。当前容器已具备工具不是删除依赖的理由；废弃或替换依赖必须显式给出原ID及证据理由。配置变化后让执行器按既有清理与重配语义处理，不自行加入删除产物或屏蔽失败的命令。

当主要目标、入口、必要依赖和修订后的配置/构建动作均已有证据，立即提交。reason只解释真实失败、最小必要修订、保留范围及尚存阻塞；不把未开始的重放称为失败，不把容器内成功称为干净重放成功，也不因历史单例成功宣称某策略普遍有效。
```

新增指导1677 UTF8字节。候选哈希：`35280b6a11f01ef5da56d438659f0492c12ea8a82c18ac3d8a3b2e0e89d14ecf`。未人工改写提案；未将此指导设为默认。

可逐字核对[原始提案JSON](../../benchmarks/fixtures/recovery-harness-proposal-v1/proposal.json)、[原共同提示](../../benchmarks/fixtures/recovery-harness-proposal-v1/prompt-before.txt)、[追加后的完整提示](../../benchmarks/fixtures/recovery-harness-proposal-v1/prompt-after.txt)。[高级模型系统提示](../../backend/packages/harness/deerflow/compile/recovery_harness.py)及[实际输入材料](../../benchmarks/fixtures/recovery-harness-proposal-v1/corpus.json)同时保留。

## 新项目池与18候选

从论文固定版本提取CompileAgentBench的100条、BUILD-BENCH附录149条、CXXCrafter Top100的100条，共349条来源记录，名称规范化后343组。这里只完成名称初步去重，不能称343个已核验独立仓库。

BUILD-BENCH v2正文称148个测试项目，而附录表7—9实际列出149条名称；原样保存，不擅自删除凑数。尚未取得能逐项对齐的官方148项版本包，因此本阶段称“论文附录来源候选池”，不称复现完整官方数据集。CXX部分仅Top100，未冒称收录全部Awesome-CPP。

下面18个候选均已解析公开仓库URL、当前commit及构建入口元数据，在本仓库全部版本化manifest/fixture的名称及URL检查中没有历史暴露命中；无命中不等于训练未见或绝对无任何手工接触。选择基于系统覆盖与来源多样性，不依据新模型成绩。还未下载源码归档、验证可构建性或形成正式实验分母。

| 构建系统 | 候选（每类6个） |
| --- | --- |
| cmake | [cglm](https://github.com/recp/cglm)、[tini](https://github.com/krallin/tini)、[wasm3](https://github.com/wasm3/wasm3)、[libhv](https://github.com/ithewei/libhv)、[ggmorse](https://github.com/ggerganov/ggmorse)、[DuckX](https://github.com/amiremohamadi/DuckX) |
| make | [massdns](https://github.com/blechschmidt/massdns)、[redsocks](https://github.com/darkk/redsocks)、[beanstalkd](https://github.com/beanstalkd/beanstalkd)、[no-more-secrets](https://github.com/bartobri/no-more-secrets)、[berkeley-softfloat-3](https://github.com/ucb-bar/berkeley-softfloat-3)、[Turbo-Base64](https://github.com/powturbo/Turbo-Base64) |
| autotools | [libmodbus](https://github.com/stephane/libmodbus)、[freesasa](https://github.com/mittinatten/freesasa)、[fsarchiver](https://github.com/fdupoux/fsarchiver)、[fastq-tools](https://github.com/dcjones/fastq-tools)、[munge](https://github.com/dun/munge)、[twemproxy](https://github.com/twitter/twemproxy) |

17项有根构建入口；berkeley-softfloat-3的作者Make入口已通过同一commit树确认在build/Linux-x86_64-GCC/Makefile，属于嵌套入口。精确提交、论文表格行号、说明位置、历史暴露指针见[项目池](../../benchmarks/fixtures/recovery-harness-proposal-v1/project-pool.json)。参考任务固定时仍须依据作者普通主目标，不能因Forge失败更换项目。

## 实现验证与边界

RecoveryHarness只在真实恢复请求中追加指导；初始规划请求逐字保持SIMPLE_PROMPT。run_simple_system通过独立recovery_harness参数接入，默认行为不变。针对性28项检查通过，包含实际本机C源码编译的失败→脚本化Agent修订→Workflow继续成功路径；不新增Provider构建或Docker比较，不把脚本响应当模型效果。修改文件Ruff及格式检查通过。最终CI与发布状态见关联PR。

风险包括新增上下文成本、先记录错误可能演变为额外核查、“可选组件”判断错误，以及恢复样本主要集中于三个来源项目。候选要求先证明可选性和主组件保留，不能把所有文档/示例错误都直接关闭。必要的再次读取仍允许，重复调用计数不直接等于无效行为。

## 用户审核与后续决定

**当前停在方案审核。** 用户确认具体策略并下达比较指令之后，再固定新增项目任务、比较身份、费用和停止规则。建议只比较H0恢复与R1恢复，初始规划固定H0，18项目各一次共36次；5美元仅为前次预算建议，本轮1美元不授权该比较。

比较后先汇报完整结果、时间/费用拆分和案例，经用户审核后才更新论文。该要求已写入仓库AGENTS.md。当前主构建及完整交付要求不变，旧E51/E52不回填，不为提案增加成功率或效果分母。

## 证据定位

- 身份：cpp-build-offline-recovery-harness-proposal-v1；[预注册](../../benchmarks/preregistrations/cpp-build-offline-recovery-harness-proposal-v1.md)。
- 原件：`/home/yiwei/.codex/outputs/forge-recovery-harness-proposal-2026-11-09-v2`；inventory canonical SHA-256 `3e6b241a0e90f0224a3bad6f520d4545b57181ae3f9bfb33be5f517c8b64e6d8`。
- 提案前准备v1快照保留；排版与元数据修正后v2首次且唯一Provider请求，未重试。
- 版本化材料：benchmarks/fixtures/recovery-harness-proposal-v1；源码入口scripts/forge_recovery_harness_proposal.py、scripts/forge_research_project_pool.py。
- 无比较结果，无论文修改；历史原件不变。
