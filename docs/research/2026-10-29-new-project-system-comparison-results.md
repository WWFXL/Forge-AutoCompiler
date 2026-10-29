# 新项目三系统比较：运行中断后的真实结果与边界

本批原计划42槽，实际保存17个原始终态（16完整、1未完整）、1个运行中断和24个未观察。它是**真实但未完整采集的系统比较**，可用于论文的新项目补充结果与可复现交付失败案例；不能写成42次实验全部完成。论文证据编号[E32](THESIS_EVIDENCE_INDEX.md#e32)，[E30](THESIS_EVIDENCE_INDEX.md#e30)仍是最新完整系统实验。

## 研究问题、方法与固定任务

身份`cpp-build-new-project-system-comparison-flash-v1`，研究当前方法在新于当前方法调试的项目中，相对强工具Agent和CXXCrafter社区版有什么完成、费用和时间取舍。七项目×两重复×三系统=42槽，每方14，六种顺序前瞻轮换。实际走到前六项目第一重复的第18槽；FiniteStateEntropy以及所有第二重复均未观察，没有换项目、补槽或重新运行失败槽。

沿[预注册](../../benchmarks/preregistrations/cpp-build-new-project-system-comparison-flash-v1.md)及[manifest](../../benchmarks/manifests/cpp-build-new-project-system-comparison-flash-v1.json)，复用E30方法和完整任务接口：Forge模型只读规划→Workflow执行→显式CMake BOOL状态核对→必要时直接动作或失败Agent；强工具Agent使用共同任务与原工具循环；CXX社区版保留Parser/Generator/Modifier/两级Judge及最多10版Dockerfile。三方统一deepseek-flash thinking low、固定镜像、依赖资源、CMake Release和2作业，所有初始读取、输出、纠错、失败及恢复费用计入。

CXX的工具、原生反馈和CPU affinity实现与Forge quota仍不同，外部验收失败不回原生Modifier；这是实现层面的系统参考，不能称同Harness单变量实验或论文原版排名。Make/Autotools不冒称具有CMake配置语义增强。

完整固定任务、原源码/测试、精确交付、同镜像完整clean replay和清理保持。jsoncpp三CTest固定串行，PEGTL完整128CTest与37默认示例，inja原2CTest及benchmark，highwayhash原三测试程序，libsigcplusplus原32个实际PASS，libsrtp原完整runtest；第18槽的这些验收没有完成观察。选择、参考与libxcrypt原生条件SKIP排除均保持[E31](THESIS_EVIDENCE_INDEX.md#e31)，未用方法结果反向改任务。

“新于当前方法调试”来自有限Git树检索；参考准备已暴露，不等于训练未见、全历史未见、独立项目族或完全盲holdout。有目的样本不作总体随机推断。

## 运行中断及保留方式

用户授权新增10美元、确认起8小时，UTC2026-10-29 07:49:37至15:49:37（北京时间15:49:37至23:49:37），无自动重试。正式启动UTC07:53:57；最后持久化的构建事件在UTC09:19:33，第18槽的原生Docker构建尚未结束。恢复时原launcher/worker均不存在，当前主机启动与可见重启记录晚于该构建事件。可确认运行丢失及随后重启，**不能确定进程终止的精确时刻与系统原因**。

第18槽有7组完整请求/响应，均为Flash且用量可复算，没有未配对请求。原`progress-18.json`、`result.json`和launcher最终收据均未产生，保持缺失；不把事后判断写成原始终态。原目录整体封存，事后[中断登记](../../benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-interruption.json)明确合并17个原终态及1条中断注释，不能当原始运行结果文件。

一个Created状态的中间容器以创建时间、父镜像和`apt-get install git`命令精确连接第18槽最后步骤，恢复时已删除并核验不存在；其他容器未动。原生清理未观察与事后清理成功分开登记。没有续跑旧身份、重试槽18或把24未观察槽补成成功/失败。

## 固定42分母的主要表

| 方法 | 计划 | 完整 | 未完整 | 运行中断 | 未观察 | 全部请求 | 估费/美元 | 已知累计分钟 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Forge状态Workflow | 14 | 6 | 0 | 0 | 8 | 23 | 0.1669023 | 18.55 |
| 强工具Agent | 14 | 5 | 1 | 0 | 8 | 94 | 0.4789485 | 21.73 |
| CXXCrafter社区版 | 14 | 5 | 0 | 1 | 8 | 43 | 0.2058042 | 41.20＋1槽缺失 |

CXX时间只包含五个有最终计时的槽，中断槽不填0、不将离线间隔当方法耗时。费用包含中断前已发的7次请求。费用按输入0.30/输出1.20美元每百万Token、全部输入按缓存未命中保守估算，非实际账单。不同完整数、未观察和截断并存，不能把本表总费或时间直接解读为42槽总体效率提升。

## 逐项目观察与共同完成的辅助结果

下表只描述第一重复实际观察；每项目每方原计划两次，未观察的第二次保留。FSE两次均未观察。

| 项目 | Forge | 强工具Agent | CXXCrafter社区版 |
|---|---|---|---|
| jsoncpp | 完整；3请求；$0.0149847 | 完整；5请求；$0.0199827 | 完整；6请求；$0.0177855 |
| pegtl | 完整；3请求；$0.0184026 | 完整；18请求；$0.1059747 | 完整；6请求；$0.0359379 |
| inja | 完整；3请求；$0.0178872 | 完整；8请求；$0.0386184 | 完整；11请求；$0.0800163 |
| highwayhash | 完整；1请求；$0.005085 | 完整；4请求；$0.0184773 | 完整；6请求；$0.0165207 |
| libsigcplusplus | 完整；4请求；$0.0607176 | 未完整；50请求；$0.2541153 | 完整；7请求；$0.0322494 |
| libsrtp | 完整；9请求；$0.0498252 | 完整；9请求；$0.0417801 | 运行中断；7请求；$0.0232944 |
| fse | 未观察 | 未观察 | 未观察 |

三方共同完整的四个配对为jsoncpp、PEGTL、inja、highwayhash，按完成结果条件化，只作效率解释，不替代固定42分母：

| 方法 | 共同完整 | 请求 | 估费/美元 | 累计分钟 |
|---|---:|---:|---:|---:|
| Forge状态Workflow | 4/4 | 10 | 0.0563595 | 10.31 |
| 强工具Agent | 4/4 | 35 | 0.1830531 | 10.84 |
| CXXCrafter社区版 | 4/4 | 29 | 0.1502604 | 32.26 |

在这四配对中，Forge相对强工具估费低69.2%、时间低4.9%；相对CXX社区实现估费低62.5%、时间低68.0%。这些不是完整七项目/两重复的效果，也不作显著性或论文原版能力判断。收益并非每项都有：jsoncpp和inja的Forge时间高于强工具，libsrtp的Forge估费高于强工具；libsigcplusplus的Forge估费高于CXX社区版。保留这些取舍，不以全指标获胜为研究继续条件。

## 规划、状态与恢复

六个Forge初始方案全部完整完成，23请求、$0.1669023均属于初始规划（含读取、输出及结构纠错），Agent恢复episode和直接配置修订均为0；初始规划平均约3.83请求、$0.02782。libsrtp初始9请求与强工具相同，但费用更高，说明请求数不等于Token费用。

配置观测6次均满足，来自三个CMake任务的重复阶段观测，不能当六个独立项目；Make/Autotools没有该观察。当前数据支持这些任务上规划后执行能够完成且在部分可比成功任务中较省费，**不提供配置直接动作或失败Agent的新增效果**。相关组件证据仍分别引用E01固定方案消融及E04恢复开关。

已登记全部六个实际观察到的Forge初始方案路径、SHA、初始费用及配置状态，原计划另八个未观察；没有只挑偏离或可修复方案。这是后续设计材料，不是新组件实验。本批没有自然配置偏离，不能把正常方案直接重复执行冒充偏差修复效果。

## 未完整案例：脏环境能构建，配方仍可能缺依赖

槽15/libsigcplusplus/强工具Agent在原工作区完成32个原测试并暂存静态库，但首次clean replay的`./autogen.sh`找不到`mm-common-prepare`，exit127。原依赖命令把apt安装和`pkg-config --modversion mm-common`连在一起：安装产生了真实副作用，`which`也找到程序，最后pkg-config检查失败，整条命令exit1。自动配方只选成功依赖步骤，因此没有纳入这条失败命令，干净环境缺安装步骤。

这不是“原作者32测试失败”。后续轨迹包含重新autogen/configure/build及大量诊断读日志，仍未得到新的完整重放，最终`GraphRecursionError`终结；50请求、791773 recorded Token、$0.2541153全部计入。它没有耗尽10美元预算，也不是主机中断槽。证据为slot-15的session、命令`command_f5611a9de48d4274b17f67bdf28c9111`、成功固定测试`command_49b91363585c4dc2bc6925128f332bf1`及replay build.log。

该案例说明有副作用的复合命令与自动配方选择之间会出现缺口，干净重放能发现原环境成功掩盖的问题。它同时反映当前强工具提交/反馈Harness的限制，不能单凭一次失败证明Workflow或状态组件普遍优于强Agent；本批不改Harness或重跑擦除该失败。

## RQ3：原轨迹分层，未观察不填值

固定42分母；按最终可观察阶段记账，前序失败仍保留。CXX源码检查把普通文件及链接合并验证。

| 最终阶段 | 通过 | 失败/拒绝 | 未观察 |
|---|---:|---:|---:|
| 最终构建与固定任务复合检查 | 17 | 0 | 25 |
| 完整原作者测试 | 17 | 0 | 25 |
| 精确交付 | 17 | 0 | 25 |
| 完整clean replay | 16 | 1 | 25 |
| 原源码/已有输入/链接保持 | 17 | 0 | 25 |
| 原尝试内清理 | 17 | 0 | 25 |

25未观察由第18槽的未到达验收与24未启动槽组成。恢复清理另有1次成功，不回填为原尝试内通过；它不意味着源码、测试或重放通过。分层只解释本队列，不估自然误接受率。

## 证据、费用和复算

全部已知160请求、2,295,808 recorded Token、保守估费$0.8516550，未知用量0。停止后的剩余预算不自动用于新身份。运行release `47061694c485f32d4a61c97111916d1add0e126e`；候选SHA `2b88330c1e748b9fe43bd54dfb41941eacf929985492ba961dc5589c74aafef4`。

原始raw `/home/yiwei/.codex/outputs/forge-new-project-system-comparison-flash-v1`，inventory `1ae33f4c1a05edf5af8db01c58ee8498f10183382e82faa48e971a6e4a42d79c`，56,317普通文件、5链接、2,027,367,445字节。封存仅新增组件快照/库存/seal，不覆盖原文件或填补原终态；347组件保持原值。原始大文件仍在本机，未建立异地备份。

操作会话`/home/yiwei/.codex/outputs/forge-new-project-system-session-2026-10-29/`保存授权、原run.log、账本、closure-v1重启/容器/显式中断登记及终态核对。封存时完整库存校验、160原响应身份/用量/费用、18排期、账本闭合和336个容器name/ID不存在核对通过；没有重跑参考资格链或产品全测。

- [版本化详细分析](../../benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-results.json)包括全42分母、语言/构建系统分层、全部初始方案登记和分层验证注释。
- [逐槽CSV](../../benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-slots.csv)记录17原终态与1中断；未观察调度保留在JSON中。
- [中断登记](../../benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-interruption.json)为事后派生，原终态仍以raw/progress为准。
- [只读提取器](../../benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-extract.py)检查派生登记的17原终态与原文件一致、slot18用量与原响应一致及库存绑定，不改原证据。

复算命令：`python3 benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-extract.py /home/yiwei/.codex/outputs/forge-new-project-system-comparison-flash-v1 --derived-result benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-interruption.json --output-dir /tmp/forge-new-project-reanalysis`。

## 论文用途及下一决定

可写：新于当前调试的六任务中Forge六次完整完成；四个三方共同成功配对呈现费用收益与较小时间差；复合依赖命令的副作用和干净重放失败是具体验证案例。它补充E30完整系统表及E01组件实验，不合并分母，也不把中断抹去。

不能写：本42次比较已完整、全七项目/两重复成功率、配置直接动作或Agent恢复在本批提高效果、普遍加速，或CXX论文原版排名。当前没有活动Provider/实验进程，旧身份保持封存。

下一项应是确认新的独立续段协议，只执行原24个从未启动槽；第18槽中断保持原样，不作为补跑对象。新身份、有效预算和时窗需明确绑定后才能继续采集，不能重用本身份。该续段不改变方法、任务或验收；完成后各身份分别保留，组合只作描述性汇总。当前先发布已经获得的正负证据，不再重做资格链。
