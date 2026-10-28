# 硕士论文实验与证据索引

核对日期：2026-10-29。研究主线：面向 C/C++ 仓库自动化构建的状态感知动作选择与验证方法研究。跟踪：[Issue #642](https://github.com/WWFXL/Forge-AutoCompiler/issues/642)。

本文回答“哪些结果可以写进论文、放在哪一部分、能够说明什么、到哪里取数”。它是论文选材入口；数值以链接的版本化报告/分析及冻结原始证据为准，当前研究阶段以 [RESEARCH_STATUS.md](../../RESEARCH_STATUS.md) 为准。

首版整理已有结果，新增实验和模型调用均为零；后续真实结果按稳定编号追加。以下用途是写作建议，不代表必须全部纳入论文，也不把工程检查重新命名为效果实验。负面结果、未完成和未观察一并保留。

## 先看哪些材料

| 论文用途 | 优先条目 | 能回答的问题 |
| --- | --- | --- |
| 完整系统比较 | [E30](#e30)，辅以[E03](#e03)、[E05](#e05) | 工具规划/模型规划＋Workflow＋失败Agent，与强工具Agent有何完成、费用和时间取舍？ |
| 失败恢复消融 | [E04](#e04) | 相同初始工具方案，允许失败后恢复是否增加完整完成？ |
| 配置状态与动作选择消融 | [E01](#e01)、[E02](#e02)，辅以[E06](#e06) | 目标保持、提前观察、直接修订各起什么作用？ |
| 完整任务验证与案例 | [E16](#e16)至[E19](#e19)，以及各批自己的分层表 | 构建退出0为何还不等于满足任务、测试和可复现交付？ |
| 外部方法参考与局限 | [E30](#e30)，辅以[E07](#e07) | 当前Forge与可运行CXXCrafter社区版有什么差异和失败案例？ |
| 成本解释与负面结果 | [E09](#e09)、[E10](#e10)、[E13](#e13)、[E20](#e20) | 为何请求少未必便宜，模板覆盖扩大未必提高效率？ |
| 历史Harness/选择器研究 | [E21](#e21)至[E23](#e23) | 过去观察到哪些收益，又为何没有直接成为当前主线结论？ |
| 系统实现与任务可执行性 | [E26](#e26)至[E28](#e28) | 接口、状态分派和参考任务是否实际可运行？ |

**最新完整结果**：[E30](#e30)完成统一条件八项目×两重复×三系统48次真实比较，Forge/强工具/CXX社区版完整16/16、16/16、13/16；Forge相对强工具估费低22.9%，累计时间低2.7%。已有系统表、组件消融和恢复实验可用于论文；下一缺口是未用于开发项目的外部有效性，不必等到所有指标占优才组织结果。准备记录[E29](#e29)继续只作工程检查。

## 阅读和取数约定

- **正文候选**：已有完整采集、明确比较/消融和可追溯结果，可按其范围进入实验章节；不表示总体显著或最终主张已获证明。
- **补充分析/案例**：用于解释机制、异质性、失败和局限，或保存历史完整实验；“补充”不等于无效。
- **工程/参考检查**：支持实现正确性和任务可执行性，可用于实现或实验设置；不能替代模型效果数据。
- **待逐项复核**：材料已登记但本次未逐份核对内容；不等于被排除，也不等于可直接引用结论。全部存量Markdown材料见[历史材料目录](THESIS_EVIDENCE_CATALOG.md)。

重复次数不等于独立项目数；各批模型、接口和任务版本不同，不把不同批次合成一个成功率或以跨批相减估计组件效果。分层分析会重复消费原运行，不能再算一份独立实验数据。费用使用各批冻结费率的估算，包含失败和恢复，不能当作实际账单；零恢复费用不代表初始规划免费。所有失败/未完成保留，未运行的测试、交付或重放记未观察。

## 正文候选：完整比较与组件消融

<a id="e30"></a>
### E30 统一条件三系统完整比较（48次）

- **问题/设计**：八个已见任务×两重复×Forge状态Workflow/强工具Agent/CXXCrafter社区版，统一Flash、完整公开任务、CMake Release、依赖资源及原测试/精确交付/完整同镜像重放，共48/48实际运行，0未观察。
- **主要结果**：完整16/16、16/16、13/16；请求84/145/109，保守估费$0.5121477/$0.6639255/$0.5554065，累计60.70/62.39/96.52分钟。Forge相对强工具估费低22.9%、请求少42.1%，累计时间低2.7%；CMake层时间几乎相同。check/simdutf的Forge估费更高，另外六项更低。
- **可写结论**：本批完整系统在相同完成数下有费用收益、时间接近；三次Forge任务经四个Agent恢复episode最终完整。初始规划71请求/$0.3874764、恢复13请求/$0.1246713，全计入。
- **边界/失败**：全部已见，两重复非独立项目；14次配置观测均满足、直接修订0，不能把本批收益当直接动作因果。CXX外部反馈不回原生Modifier、工具循环/CPU约束实现不同，不称同Harness或论文原版排名。三项CXX未完整分别为交付歧义、Git索引核验拒绝、指定测试入口缺失；完整原测试46通过/0实际失败/2未观察，交付45通过1拒绝2未观察，replay45通过3未观察。三方共同成功13配对仅辅助，按结果条件化。
- **定位**：`cpp-build-unified-system-comparison-flash-v1`；[结果报告](2026-10-29-unified-system-comparison-results.md)、[版本化分析](../../benchmarks/analyses/cpp-build-unified-system-comparison-flash-v1-results.json)、[逐槽CSV](../../benchmarks/analyses/cpp-build-unified-system-comparison-flash-v1-slots.csv)、[只读提取](../../benchmarks/analyses/cpp-build-unified-system-comparison-flash-v1-extract.py)、[预注册](../../benchmarks/preregistrations/cpp-build-unified-system-comparison-flash-v1.md)。raw `/home/yiwei/.codex/outputs/forge-unified-system-comparison-flash-v1`；inventory `138294da578cc3ab326e546bf678d4f81fef770830e2de71fb90b1637f500582`。系统结果与E01组件消融分开解释，不合并分母。

<a id="e01"></a>
### E01 固定初始方案的状态观察与直接动作消融（30槽）

- **问题/设计**：五份已见自然初始方案×两次新容器重复×三处理；来自simdutf/snappy/yaml-cpp，包含配置偏离和满足。相同方案下比较编译后Agent、编译前检查＋Agent、编译前检查＋直接修订＋Agent。模型deepseek-flash。
- **主要结果**：完整完成9/10、10/10、10/10；新增恢复请求23、27、0；含相同历史规划费的估费分别$0.5102754、$0.5213778、$0.3386424；新执行累计45.58、48.92、42.28分钟。四次直接修订全部完整通过；正常层18/18无额外恢复或修订。
- **可写结论**：实际配置与显式目标比较能提前发现偏差；有作者选项声明及真实BOOL缓存依据的直接动作，在这些案例中减少Agent恢复。提前交Agent本身不保证省费或省时。
- **边界/失败**：同一方案固定，恢复后的动作可以不同；按历史状态选样，不估自然错误发生率或未见泛化。共同完成的9配对中时间低12.8%、含规划费低28.1%仅为按结果条件化的辅助分析。唯一未完成为后置Agent的simdutf：额外路径/测试程序数量断言误拒后耗尽两次handoff，原完整测试与交付/重放未观察。新执行时间不含重新规划。
- **定位**：`cpp-build-fixed-plan-state-increment-flash-v1`；[结果报告](2026-10-28-fixed-plan-state-increment-results.md)、[版本化分析](../../benchmarks/analyses/cpp-build-fixed-plan-state-increment-flash-v1-results.json)、[预注册](../../benchmarks/preregistrations/cpp-build-fixed-plan-state-increment-flash-v1.md)。原始目录：`/home/yiwei/.codex/outputs/forge-fixed-plan-state-increment-flash-v1`；inventory `dbc003f5842980b2a2e5b76b4854f3ed1b650d08a007083402a8ab1437e6d903`。

<a id="e02"></a>
### E02 目标保持、实际配置状态三处理消融（18槽）

- **问题/设计**：simdutf/snappy/yaml-cpp×两重复×共同当前版/仅目标/目标＋配置状态；共同修复后的Harness、deepseek-flash，各臂独立生成初始方案。
- **主要结果**：各6/6完整；请求54/42/46，估费$0.2696118/$0.2023626/$0.2377458，累计34.43/27.66/32.63分钟。仅目标相对当前版低费24.9%、低时19.7%；状态版相对仅目标高费17.5%、高时18.0%。snappy出现一次自然偏离→直接改BOOL→完整完成，0恢复请求。
- **可写结论/边界**：目标保持在本批有价值，状态动作确实发生，但没有相对仅目标的整体优势。独立初始方案、构建类型/依赖动作存在差异，不能把全差值归于状态检查；一次直接修订不估平均收益。这是E01固定方案设计的动机来源，两个实验分开报告。
- **定位**：`cpp-build-goal-state-component-ablation-flash-v1`；[报告](2026-10-28-goal-state-component-results.md)、[分析](../../benchmarks/analyses/cpp-build-goal-state-component-ablation-flash-v1-results.json)、[预注册](../../benchmarks/preregistrations/cpp-build-goal-state-component-ablation-flash-v1.md)。raw：`/home/yiwei/.codex/outputs/forge-goal-state-component-ablation-flash-v1`；inventory `8e1b481aa8a059e46e4ef325a2a8fadeb6db27b482d9d723d4cfe3d66273955d`。

<a id="e03"></a>
### E03 Flash完整任务三策略比较（12槽）

- **问题/设计**：rang/ELFIO×两重复×工具规划Workflow/模型规划Workflow/强工具Agent；统一deepseek-flash与完整任务。两者均为CMake的header-only库原作者编译端点。
- **主要结果**：各4/4完整；请求20/19/44，估费$0.1204590/$0.0886800/$0.1684407，累计7.58/5.45/6.30分钟。模型规划相对强工具低费47.35%、低时13.42%；工具规划低费28.49%、耗时高20.31%。工具四槽均失败后恢复，模型四槽均初始方案完成。
- **可写结论/边界**：方案执行可有费用/时间收益，工具与模型规划有项目相关取舍。两个已见CMake任务不代表跨系统C++总体；强工具具有自己的控制循环和工具能力，是完整策略比较，不是三者Harness完全相同的单变量实验。
- **定位**：`cpp-build-library-strategy-comparison-flash-v1`；[报告的“三策略比较”部分](2026-10-27-flash-thesis-experiment-results.md)、[分析](../../benchmarks/analyses/cpp-build-library-strategy-comparison-flash-v1-results.json)、[冻结协议](../../benchmarks/manifests/cpp-build-library-strategy-comparison-flash-v1.json)。raw：`/home/yiwei/.codex/outputs/forge-library-strategy-comparison-flash-v1`；inventory `4e29253cddd262a91533846131efd533d77dd4a55653695eea5cca01168846c6`。

<a id="e04"></a>
### E04 相同工具方案、有/无失败Agent恢复消融（10槽）

- **问题/设计**：snappy/simdutf/yaml-cpp/libtommath/tinyxml2，每项一对新鲜会话；初始方案和失败前执行前缀相同，仅切换失败后是否允许Agent修订，模型deepseek-flash。
- **主要结果**：无恢复2/5完整，有恢复4/5完整；新增完成snappy/yaml-cpp，simdutf/tinyxml2均无需模型完成，libtommath两臂均未完成。恢复共10请求/$0.0590439，包含libtommath失败的4请求/$0.0219207。
- **可写结论/边界**：在这五个固定任务中，恢复开关增加了完整完成，且正常任务不必调用模型。每项目一对、已见并有预期失败暴露，不估总体恢复率。libtommath因共享引用错误进入材料停止，不能解释为模型不能修复。不可与E15旧无恢复五槽配成十对。
- **定位**：`cpp-build-tool-recovery-ablation-flash-v1`；[报告的“有恢复／无恢复消融”部分](2026-10-27-flash-thesis-experiment-results.md)、[分析](../../benchmarks/analyses/cpp-build-tool-recovery-ablation-flash-v1-results.json)、[冻结协议](../../benchmarks/manifests/cpp-build-tool-recovery-ablation-flash-v1.json)。raw：`/home/yiwei/.codex/outputs/forge-tool-recovery-ablation-flash-v1`；inventory `6b7785602cabe6ed4eb6499e3717f31b0aa58ef7edce6449425be0cee09b4c33`。

<a id="e05"></a>
### E05 六项目三策略独立重复比较（36槽，历史Pro批次）

- **问题/设计**：check/simdutf/snappy/yaml-cpp/libtommath/tinyxml2×两重复×三策略，包含CMake/Make/Autotools，沿用当时Pro模型和共同完整任务。
- **主要结果**：各12/12完整；工具/模型/强工具请求26/46/115，估费$0.68970924/$1.16324472/$1.80520164，累计44.70/52.67/48.81分钟。工具相对强工具低费61.79%、低时8.43%；模型低费35.56%、耗时高7.91%。工具4次零模型完成；六次工具Workflow失败修订后完成。
- **可写结论/边界**：已有完整跨构建系统任务比较和成本/时间取舍。六项目中四个C++均为CMake，另两个C覆盖Make/Autotools；全部已见，不宣称跨系统C++泛化。没有同批无恢复对照，恢复轨迹不等于恢复因果增益；不与Flash批次相减估模型效果。
- **定位**：`cpp-build-strategy-replication-v1`；[报告](2026-10-23-strategy-replication-results.md)、[分析](../../benchmarks/analyses/cpp-build-strategy-replication-v1-results.json)、[预注册](../../benchmarks/preregistrations/cpp-build-strategy-replication-v1.md)。raw：`/home/yiwei/.codex/outputs/forge-strategy-replication-v1`；inventory `68ddf187317a716f6eb4b98de9a234b948b3c93d927705bc6885e83f1fdeb9f7`。

## 补充分析与案例：保留收益、代价和失败

<a id="e06"></a>
### E06 配置目标与状态增强首轮配对（24槽）

- **设计/结果**：六已见任务×两版×两重复；当前9/12、增强10/12完整；估费$0.4510923/$0.5063022，累计42.72/52.06分钟。三项预定义CMake作用范围均5/6，增强低费21.8%、低时7.6%；实际配置12次均满足，直接修订0。
- **用途/边界**：用于说明领域作用范围和整体取舍，保留五项接口/材料未完成案例；不能证明直接动作效果。旧五失败不因后续接收修复而改成功，不与E02/E01池化。
- **定位**：`cpp-build-goal-state-paired-flash-v1`；[报告](2026-10-27-goal-state-paired-results.md)、[分析](../../benchmarks/analyses/cpp-build-goal-state-paired-flash-v1-results.json)。raw：`/home/yiwei/.codex/outputs/forge-goal-state-paired-flash-v1`；原预注册与inventory见报告。

<a id="e07"></a>
### E07 当前Forge与CXXCrafter社区版参考（两个身份、六次实际观察）

- **设计/结果**：原六槽身份只观察simdutf两槽、四槽未启动；独立短项目身份观察tinyxml2/check四槽。六次实际观察中CXX完整2、Forge方法未完成1、时窗截断3。simdutf中Forge反复偏离配置目标，CXX完整通过；是需要保留的真实反例。
- **用途/边界**：方法动机、外部参考和失败分析；暂不作公平系统排名。任务呈现、反馈、测试并行及调度有差异；社区代码带运行修复，不能称论文原版复现。三项截断不能一律记方法失败，也不能凭较短费用/时间宣称效率优势。
- **定位**：`cpp-build-current-cxx-reference-flash-v1`、`cpp-build-current-cxx-short-reference-flash-v1`；[报告](2026-10-27-current-cxx-reference-results.md)、[原身份分析](../../benchmarks/analyses/cpp-build-current-cxx-reference-flash-v1-results.json)、[独立短项目分析](../../benchmarks/analyses/cpp-build-current-cxx-short-reference-flash-v1-results.json)。raw分别为`/home/yiwei/.codex/outputs/forge-cxx-current-reference-v1`、`/home/yiwei/.codex/outputs/forge-cxx-short-reference-v1`。

<a id="e08"></a>
### E08 早期三系统方案/工具Agent配对（24槽）

- **设计/结果**：六仓库×两重复×双臂，双方12/12完整；请求60/105，估费$1.26334296/$1.62595884，累计2840.27/3195.20秒。方案臂0恢复；工具臂11/12出现共19次提交配方ID拒绝后纠正。
- **用途/边界**：完整路径的早期正向结果及接口成本讨论。费用关联组重采样范围跨0，不宣称稳定总体成本优势；手工ID接口负担混入差异，不代表成熟工具Agent排名。没有恢复动作，不能证明状态恢复效果。
- **定位**：`cpp-build-plan-agent-paired-comparison-v1`；[报告](2026-10-20-build-plan-agent-paired-comparison-results.md)、[预注册](../../benchmarks/preregistrations/cpp-build-plan-agent-paired-comparison-v1.md)。raw：`/home/yiwei/.codex/outputs/forge-plan-agent-paired-real-v1`；派生分析位置见报告。

<a id="e09"></a>
### E09 自动配方溯源强接口探针（12槽，费用反例）

- **设计/结果**：三已见项目×两重复×双臂；双方5/6完整。plan/tool请求37/50、估费$0.79509408/$0.71376360、累计1095.568/840.297秒。plan请求少26%，但费用高约11.4%、耗时高约30.4%。
- **用途/边界**：保留“少请求不等于低成本”反例。工具自动维护ID后仍有差异，但跨E08/E09变化不是接口纯因果。libverto有5次真实恢复请求未交修订，不能误写成未调用恢复模型。
- **定位**：`cpp-build-auto-provenance-probe-v1`；[报告](2026-10-20-build-auto-provenance-probe-results.md)。raw：`/home/yiwei/.codex/outputs/forge-auto-provenance-real-v1`；逐响应费用分解见[E20](#e20)。

<a id="e10"></a>
### E10 早期三策略36个逻辑槽位（两个版本身份）

- **设计/结果**：原身份16观察/20未观察，新独立续段只执行原20未观察位置，未重跑前16。描述性汇总：强工具9/12、方案9/12、方案＋规则8/12完整；估费$1.67860968/$2.09666952/$1.72972404。规则激活0；方案请求少9.2%，费用反而高24.9%。
- **用途/边界**：费用反例、接口转写负担、失败分类和研究演进。跨身份只作披露版本差异的描述，不称原v1完整或单一版本因果；规则未激活不估规则增量。六项主要为C库，不泛化大型C++。
- **定位**：`cpp-build-full-strategy-comparison-v1`及`cpp-build-full-strategy-cleanup-continuation-v1`；[报告](2026-10-20-build-full-strategy-comparison-results.md)。raw：`/home/yiwei/.codex/outputs/forge-full-strategy-real-v1`、`/home/yiwei/.codex/outputs/forge-full-strategy-real-continuation-v1`；对应协议、独立inventory及跨身份分析位置均列在报告。

<a id="e11"></a>
### E11 观察接口三策略完整比较v2（12槽）

- **设计/结果**：libpng/check/libtommath/libsodium×三策略各一次；工具/模型/强工具完整3/4、4/4、3/4，请求21/24/37，估费$0.44570064/$0.54394032/$0.56717496。libsodium工具0模型完整；三次Workflow修订后完整。
- **用途/边界**：工具局部价值及完成/耗时取舍。工具拒答后三项目首次Agent输入相同，不能把随机轨迹差归于省掉规划。保留v1 HTTP402及未知用量，不与v2合并结果。
- **定位**：`cpp-build-observed-plan-comparison-v2`；[报告](2026-10-20-observed-plan-recharged-results.md)。raw：`/home/yiwei/.codex/outputs/forge-observed-plan-comparison-v2`。

<a id="e12"></a>
### E12 CMake C++三策略比较（18槽）

- **设计/结果**：yaml-cpp/simdutf/snappy×两重复×三策略；工具/模型/强工具5/6、4/6、6/6完整，估费$0.33836088/$0.38033424/$0.73215120。simdutf工具两次零模型完整；三次Workflow交接但0成功修订。
- **用途/边界**：早期C++完整策略取舍和恢复材料限制；不能主张可靠性领先或恢复收益。三项目均已见CMake、存在共享测试来源；低费用含失败，不能解释成同等完成下的效率。
- **定位**：`cpp-build-cxx-comparison-v1`；[报告](2026-10-21-cxx-comparison-results.md)。raw：`/home/yiwei/.codex/outputs/forge-cxx-comparison-v1`；分层再分析见[E18](#e18)。

<a id="e13"></a>
### E13 任务指定模板消融（6槽，未见总体收益）

- **设计/结果**：三已见CMake任务×保守模板/任务指定模板；均3/3完整、各14请求。指定模板估费高9.37%、累计耗时高2.51%，恢复次数1→2。
- **用途/边界**：模板覆盖与恢复成本的取舍，支持保留模型规划参照。解除多入口拒答未必省费；三次修订后清空build重走后缀，不证明最小增量收益。
- **定位**：`cpp-build-task-selected-comparison-v1`；[报告的“六槽真实消融”部分](2026-10-21-task-selected-template-results.md)。raw：`/home/yiwei/.codex/outputs/forge-task-selected-comparison-v1`；报告前半三槽脚本资格不计入这六槽。

<a id="e14"></a>
### E14 C++ Make/Autotools比较与生成文件边界（18槽）

- **设计/结果**：tinyxml2/libconfig×三重复×三策略；tinyxml2九槽全完整，工具三次零模型；libconfig九槽均在bootstrap后改写原生成模板/辅助文件而被旧原文件合同拒绝，后续编译和测试未观察。
- **用途/边界**：默认Make路径局部价值、任务边界的局限。九项源码合同拒绝不能写成功能测试失败。用户后续允许明确生成文件的边界B只适用于新协议，不回填旧18槽。
- **定位**：`cpp-build-cxx-cross-system-comparison-v1`；[结果](2026-10-21-cxx-cross-comparison-results.md)、[后续边界B决定](2026-10-21-generated-file-boundary-b.md)。raw：`/home/yiwei/.codex/outputs/forge-cxx-cross-system-comparison-v1`。

<a id="e15"></a>
### E15 Pro扩展任务比较的范围缺陷与无恢复观察

- **设计/结果**：rang/ELFIO三策略12次尝试，原工程strict11，按文字完整范围仅10完成、1漏示例、1 HTTP402未进入方法；不是公平完整三方排名。另立五任务无恢复观察，2/5完整、0模型；当时预定恢复十槽未观察。
- **用途/边界**：任务义务遗漏、Provider停止与构建成功终点区别。漏示例槽原测试和replay通过仍不满足完整范围，原布尔不回写；不是自然误接受率。后来E03/E04独立重新采集，不把两批凑成配对或修改旧分母。
- **定位**：`cpp-build-library-strategy-comparison-v1`、`cpp-build-tool-no-recovery-observation-v1`等；[报告](2026-10-23-library-expansion-results.md)、[比较分析](../../benchmarks/analyses/cpp-build-library-strategy-comparison-v1-results.json)、[独立无恢复分析](../../benchmarks/analyses/cpp-build-tool-no-recovery-observation-v1-results.json)。raw分别为`/home/yiwei/.codex/outputs/forge-library-strategy-comparison-v1`、`/home/yiwei/.codex/outputs/forge-tool-no-recovery-observation-v1`；参考与失败身份见报告末表。

<a id="e16"></a>
### E16 分层验证回顾（43行、四队列）

- **设计/结果**：固定人工参考10、受控控制7、人工参考2、真实模型24，各队列分开提取构建/测试/交付/源码/replay事实。保留空测试、字节漂移、遗漏bootstrap、过期测试凭证等七个具体案例。
- **用途/边界**：可写验证研究与案例表：exit0、测试成功和完整交付是不同终点。队列有人工和受控样本，不能合并算自然误接受率；并列层状态不是串行漏斗。E19七控制已包含在此，不能重复计独立样本。
- **定位**：`cpp-build-validation-evidence-audit-v1`；[报告](2026-10-20-build-validation-evidence-audit-results.md)、[分析协议](../../benchmarks/analyses/cpp-build-validation-evidence-audit-v1.json)。成功分析raw：`/home/yiwei/.codex/outputs/forge-validation-evidence-audit-v1-attempt-002`；首次失败保留。

<a id="e17"></a>
### E17 自然失败相关队列的固定14行分层回顾

- **设计/结果**：完整消费E09十二臂与libverto旧/新恢复各单例，分为12/1/1三队列；其中E09构建12过、完整测试11过1败、交付/replay各10过2未观察；新libverto构建过、六测试仍失败。
- **用途/边界**：展示真实轨迹中build、有效测试、交付的缺口；不是14个独立自然项目，不能和E09、E24重复计样本，也不与E16合成57次运行。
- **定位**：`cpp-build-validation-natural-audit-v1`；[报告](2026-10-20-build-validation-natural-audit-results.md)。raw：`/home/yiwei/.codex/outputs/forge-validation-natural-audit-v1`。

<a id="e18"></a>
### E18 C++两个固定队列的分层验证（18与6分别报告）

- **设计/结果**：E12十八槽build均过，固定检查15过3败，作者完整测试/交付/replay各15过3未观察；E13六槽最终各层均通过，但保留中途三次修订。
- **用途/边界**：成功编译不足以满足依赖功能和测试义务；失败与尚未执行可分开定位。重复消费E12/E13原运行，不新增24个独立观察，不由全通过认定某验证层无必要。
- **定位**：`cpp-build-cxx-fixed-cohort-validation-audit-v1`；[报告](2026-10-21-cxx-validation-layers-results.md)、[分析](../../benchmarks/analyses/cpp-build-cxx-fixed-cohort-validation-audit-v1-results.json)。原始输入目录为E12/E13；提取规则及收据位置见报告。

<a id="e19"></a>
### E19 状态变化与验证正负控制（7槽、零Provider）

- **设计/结果**：miniz/pigz/libite三个正常控制完整；空测试、交付字节漂移、遗漏bootstrap、权威外部configure四负控制按预期被拒，7/7预期观察成立。
- **用途/边界**：方法章节的受控机制验证和具体反例；不是七次构建全成功，不估自然误接受率或Agent修复能力。属于零Provider受控实验，不是普通pytest测试数；E16已消费这些原运行。
- **定位**：`cpp-build-state-validation-controls-v1`；[报告](2026-10-20-build-state-validation-controls-results.md)。raw：`/home/yiwei/.codex/outputs/forge-build-state-controls-v1`。

<a id="e20"></a>
### E20 输入/输出与规划/恢复费用分解（36臂、252原响应）

- **设计/结果**：只读重算E08的24臂、E09的12臂。E09方案输入费用节省$0.08340156，输出多$0.16473204，故总费多$0.08133048。核对libverto为4初始＋5真实恢复请求。
- **用途/边界**：费用分解图、失败恢复开销和请求数局限。后验算术分解不产生新的效果样本；没有输出语义标注，不能把增量全归于JSON或思考文本，更不能直接断言缩短提示就会省费。
- **定位**：`cpp-build-token-cost-attribution-audit-v1`；[报告](2026-10-20-build-token-cost-attribution-audit-results.md)。raw：`/home/yiwei/.codex/outputs/forge-token-cost-attribution-audit-v1`。

<a id="e21"></a>
### E21 历史H0/H1 Harness确认性复现v3（54臂）

- **设计/结果**：受控checkpoint、27配对；H0/H1完整19/27、22/27，估费$1.507782/$0.753661，低50.0%。分系统CMake4/9→9/9、Make9/9→8/9、Autotools6/9→5/9；单侧下界-0.111，未达到原-0.10非劣界。
- **用途/边界**：历史Harness组件、费用收益与不均衡可靠性的完整结果，负面判据一并保留。原决定停止其作为主机制；不重新包装为当前Workflow组件效果，不以硕士目标修改原阈值。不达当时判据不等于数据不能用于论文分析。
- **定位**：`cpp-progress-aware-harness-comparison-v3-authorized`；[报告](../../benchmarks/reports/cpp-progress-aware-harness-comparison-v3-authorized.md)、[机器结果](../../benchmarks/reports/cpp-progress-aware-harness-comparison-v3-authorized.json)。raw：仓库下`.compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v3`；manifest及inventory见原结果。

<a id="e22"></a>
### E22 历史H0/H1/H2 Runtime v6正式比较v2（18臂）

- **设计/结果**：三个冻结项目族×两重复×三臂，各6/6完整；估费$0.158667/$0.088058/$0.087804。H2 closure执行6次，拒绝/repair window均0；原决定为非劣但机制未激活。
- **用途/边界**：解释增加检查不等于已证明恢复收益。可以保存整体比较，不能在未触发修复时宣称H2恢复增量；与失败/部分的v1分开。
- **定位**：`cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v2`；[报告](../../benchmarks/reports/cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v2.md)、[机器结果](../../benchmarks/reports/cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v2.json)。raw：仓库下`.compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v2`。

<a id="e23"></a>
### E23 历史Jev受控失败正式比较v6（72臂）

- **设计/结果**：冻结受控失败、当时未见项目族，三臂各24；AlwaysAgent/规则＋Agent/Jev＋Agent完整10/24、13/24、22/24；Jev路径相对AlwaysAgent估费低89.6%。原报告记录直接动作45、错误直接动作16、升级43，不能只摘成功终点隐去错误动作。
- **用途/边界**：受控场景的历史选择器研究或附录，不是当前自然仓库状态分类器效果。后续自然适用性/停止决定仍以当前状态及知识库为准；受控正向结果不能覆盖自然失败边界。
- **定位**：`cpp-jev-formal-comparison-v6`；[报告](../../benchmarks/reports/cpp-jev-formal-comparison-v6.md)、[机器结果](../../benchmarks/reports/cpp-jev-formal-comparison-v6.json)。raw：仓库下`.compile-sessions/benchmark-evidence-jev-formal-comparison-v6`；旧失败版本也在历史目录登记。

<a id="e24"></a>
### E24 libverto最小配置修订失败（零模型单例）

- **设计/结果**：原静态only配置build退出0、六测试全失败；仅改configure为同时enable-shared/enable-static，再make退出0但耗时0.17秒、Nothing to be done，六测试仍全失败。交付/replay未观察。
- **用途/边界**：逻辑执行记录失效与物理缓存/产物失效不同，是需要保留的负面机制案例；不声称根因已穷尽、清理重建已证明足够或Agent修复失败。
- **定位**：`cpp-build-libverto-natural-recovery-v2`；[报告](2026-10-20-build-libverto-natural-recovery-v2-results.md)。raw：`/home/yiwei/.codex/outputs/forge-libverto-natural-recovery-v2`；E17对它作了回顾，不重复计样本。

<a id="e25"></a>
### E25 rtorrent困难任务：真实双树编译但测试准备未闭合

- **设计/结果**：独立生成/观察分离探针一槽；9请求/$0.26768016，libtorrent和rtorrent真实编译并暂存两个ELF，12个必需测试程序未构建，0作者叶实际执行；恢复请求前受旧时间准入阻止，交付验收/replay未观察。
- **用途/边界**：复杂依赖、生成步骤与测试准备的局限案例。不能把暂存ELF称完整任务成功，也不能把未执行测试称功能失败。报告中六独立阶段累计12槽仅是开发流水，不是公平策略比较。
- **定位**：`cpp-build-rtorrent-generation-observation-probe-v1`；[报告](2026-10-22-rtorrent-generation-observation-results.md)。raw：`/home/yiwei/.codex/outputs/forge-rtorrent-generation-observation-probe-v1`。

## 工程与参考检查：支持实现说明

<a id="e26"></a>
### E26 固定方案三处理六槽分派检查

- **观察**：snappy后置组先build再交接、前置Agent组build前交接，两者在真实Provider前主动停止；直接组修订后完整完成，yaml-cpp三组正常完整。0真实Provider。
- **用途/边界**：说明E01入口与分派路径实际可用；主动停在模型前不算方法失败，也不能估Agent恢复收益。E01真实30槽才是对应效果采集。
- **定位**：`cpp-build-fixed-plan-state-dispatch-check-v1`；[设计及开发结果](2026-10-28-fixed-plan-state-increment-design.md)、[分析](../../benchmarks/analyses/cpp-build-fixed-plan-state-dispatch-check-v1.json)。raw：`/home/yiwei/.codex/outputs/forge-fixed-plan-state-dispatch-check-v1`。

<a id="e27"></a>
### E27 共同候选接收修复与原案例脚本回放

- **观察**：三份原JSON候选可装配、自由说明仍拒绝；tinyxml2一份原候选在脚本模型下完整构建/测试/交付/replay，0真实Provider。非法引用路径错误反馈后可以继续读取。
- **用途/边界**：定位共同接口问题，支持后续组件比较设置；不是新模型成功率提升，不把E06旧失败改成功，不把三份可装配都写成可构建。
- **定位**：[报告](2026-10-28-common-harness-repair-and-ablation.md)、[派生摘要](../../benchmarks/analyses/cpp-build-common-harness-repair-v1.json)。回放：`/home/yiwei/.codex/outputs/forge-common-harness-session-2026-10-28/original-case-replay-v1`。

<a id="e28"></a>
### E28 rtorrent完整任务参考及干净重放

- **观察**：独立reference-v5原构建和重放均执行12原程序/323叶测试、精确两ELF交付；保护818作者文件，40生成文件SHA满足声明，0模型费用。前四个失败参考分别保留。
- **用途/边界**：任务/依赖/生成文件边界及验收可执行性的依据，可进入实验设置；人工参考通过不代表模型方法成功。用户起初的主项目三个程序与依赖九个程序合计12个，不能遗漏依赖测试。
- **定位**：[完整参考报告](2026-10-21-rtorrent-reference-results.md)。各独立参考身份、协议、raw和inventory见该报告的身份表及证据部分，不合成旧身份全部通过。

<a id="e29"></a>
### E29 统一条件三系统比较的执行准备（工程检查）

- **设计/用途**：固定八个已见项目×两重复×Forge状态Workflow/强工具Agent/CXX社区版，共48槽；统一完整目标、CMake Release、依赖、并行环境和完整验收。用于论文实验设置；后续48次真实效果单列[E30](#e30)，不升级本条开发检查。
- **开发检查**：独立tinyxml2三个入口均实际构建、原测试、精确交付、完整replay及cleanup通过，8脚本响应、0真实Provider/Token/模型费。只证明新适配可执行，不能把脚本响应耗时当方法优势。代码、候选草稿和原始证据保留，未重跑旧参考链。
- **边界/定位**：全部已见，CXX原生反馈与工具权限不同，不称同Harness或论文原版。[设计与开发结果](2026-10-29-unified-system-comparison-design.md)、[预注册](../../benchmarks/preregistrations/cpp-build-unified-system-comparison-flash-v1.md)、[开发分析](../../benchmarks/analyses/cpp-build-unified-system-dispatch-check-v1.json)。raw：`/home/yiwei/.codex/outputs/forge-unified-system-preparation-2026-10-29/dispatch-check-v1`；inventory `2a1346e5975b3d516b790c73bf30be04758bf95098c0a3d61dac55038502ae72`。新Provider须新授权，不续旧30槽。

## 写作时的图表取材

| 建议图表 | 数据条目 | 必须随图表保留的说明 |
| --- | --- | --- |
| 三策略完成/费用/耗时表 | E30主表，E03与E05分别补充 | 模型与任务版本不同，不合并估效果；完整策略工具能力有差异 |
| 恢复开关配对表 | E04 | 每项目一对；包含失败恢复费用和不触发恢复的任务 |
| 相同方案三处理消融表 | E01 | 全30槽为主，共同完成9配对只作辅助；时间不含新规划 |
| 目标/状态组件取舍表 | E02，E06作前序补充 | 各臂独立规划；不能把差异全归实际状态观察 |
| 状态—证据—动作案例图 | E01的snappy/simdutf，E24作反例 | 读取实际缓存、显式目标、作者声明；复杂/未知仍交Agent |
| 分层验证表与失败位置图 | E16/E17/E18及各批分层表 | 原分母、未观察和重叠来源；不能池化自然误接受率 |
| 输入/输出与初始/恢复费用图 | E20及E03/E05分阶段表 | 各批冻结单价、失败成本；请求数不是费用代理 |
| 局限与负面案例表 | E07/E09/E13/E14/E15/E24/E25 | 时窗截断、任务合同拒绝、功能失败分别表述 |

## 后续维护：每个结果发布时做一次简短登记

1. 新增真实比较、消融、可复算分析或有解释价值的失败时，在本索引追加稳定编号；同一运行的再次分析注明与父条目重叠。
2. 每项至少写清问题/设计、计划与实际分母、关键结果、论文用途、可支持/不可支持结论，以及报告/分析/协议和raw指针。旧原始证据、失败和统计终点不改。
3. 同步[历史材料目录](THESIS_EVIDENCE_CATALOG.md)的新文件入口；无需为登记重跑构建、Provider、产品全测或旧证据全量审计。这里只核对本次报告与引用。
4. `RESEARCH_STATUS.md`和知识库保留本索引的链接；详细数值与原始证据不再复制成新的竞争事实源。研究阶段继续由原状态入口决定。
5. 只有新证据支持时才调整“正文候选/补充/工程”用途，并写明理由；被新结果限制的旧结论保留日期和边界，不删除负面数据。尚未逐项复核的历史材料保持可检索。

**保存范围**：本索引、历史目录、报告和版本化分析受Git版本管理；原始运行证据继续位于其封存目录。本次没有复制、迁移或建立原始大文件的异地备份；目录可定位不等于已经建立第二份备份。
