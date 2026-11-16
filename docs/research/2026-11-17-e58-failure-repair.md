# E58未完成项目归因与共同修复

本轮为工程修复与真实构建验证。用户要求先分析E58未完成项目、区分共同基座与Agent决策原因，完成修复后再做集中比较。跟踪Issue #815，原E58的36槽、失败和论文v0.12均保留，不在原身份中续跑。

## 原轨迹的责任划分

| 项目 | 原实际执行 | 未完成的直接原因 | 修复位置 |
|---|---|---|---|
| smenu（槽5/6） | configure/make成功，主要程序已生成 | 程序在处理版本选项前打开/dev/tty；原检查无控制终端。实际版本输出为Version，原检查还错误要求smenu字样 | 独立参考提供PTY，并核对作者版本输出和退出0 |
| quickjs（槽9/10） | make成功；算术表达式退出0并输出2 | 独立参考把产物名qjs当成表达式stdout要求 | 保留原表达式和异常检测，检查输出2 |
| zstd（槽21/22） | make成功；--version退出0 | 真实输出Zstandard CLI，参考却要求小写zstd字面子串 | 检查作者真实版本标记，保留退出0要求 |
| libtasn1（槽29/30） | 原组新克隆gnulib后README-release补丁不兼容；更新组用系统gnulib，bootstrap因gtkdocize缺失失败 | Agent初始依赖选择/准备有遗漏，但更新组已生成补gtk-doc-tools方案。共同执行器插入175308字节清理脚本，其中tests/reproducers.c误中/repro拦截，退出126；巨型命令再进入必要恢复上下文导致容量停止 | 原输入清单移至执行侧；清理命令只引用清单及摘要；修复/repro路径边界；用原已提出的恢复方案验证执行链路 |

依据：原件`/home/yiwei/.codex/outputs/forge-harness-update-comparison-flash-2026-11-17-v1`内对应slot的`result.json`、`agent/simple-actions-*.json`、session命令记录和日志。原组libtasn1失败日志明确为gnulib-tool的README-release补丁失败，更新组明确为autoreconf调用gtkdocize失败；两者清理均为policy_rejected/126，尚未执行补救指令。

smenu作者源码`smenu.c:10457–10472`先打开/dev/tty，版本动作`8892–8906`输出Version后退出0。QuickJS原检查命令本身要求1+1等于2且输出2；zstd原实际版本输出已在日志中。这三处修正改变新运行的独立参考，不修改冻结E58参考，也不让Agent改写裁判。

## 共同机制修复

`generated_inputs.py`将排序后的原输入相对路径写入工作区侧`.forge-source-inputs.json`。Workflow在首次构建前建立清单；清理动作仅包含固定Python逻辑和清单SHA-256，长度859字节，不随文件数量增长，不再把全部路径装入方案和恢复上下文。清单缺失或摘要变化时在删除文件前停止。

干净重建在原源码解压/检出后、任何构建动作之前重新建立同一清单。后续成功配方保留实际清理动作和依赖安装指令；不会在已经生成文件后才扫描并把生成物当成原输入。原文件仍按原输入集合保留，文件变化按共同后验策略另行记录。

阶段命令检查仅识别完整/repro路径及其子路径，允许tests/reproducers.c这样的普通文件名；未取消真实/repro访问限制、严格Shell及既有阶段规则。

## 新工程运行

身份`cpp-build-e58-failure-repair-v1`，入口`scripts/forge_e58_failure_repair.py`。同原归档、任务目标与镜像；前三项沿用原更新组构建动作，只修正独立参考。libtasn1沿用槽30初始动作，复现缺gtkdocize，再由零Provider脚本提交原槽30已经生成的第二份补包方案，观察恢复、交付和原归档干净重建。

本轮没有Provider请求和新增模型费用。脚本响应仅用于验证工程链路，不代表模型在新版本上再次自主作出了相同决策。原运行的方案、参考、失败及成本不回填；本轮不增加模型效果或独立项目分母。

首轮工程运行v1中，前三项完成；libtasn1成功复现缺gtkdocize并越过原基座阻断，但默认make随后在fuzz/corpus2array.c包含gnulib的string.h/stddef.h时报告“Please include config.h first”。这是原轨迹尚未到达的新编译错误：辅助程序未先包含生成配置头，不能把它计为原来已观察到的失败，也不应再归因于Workflow拒绝执行。

随后采用make的CPPFLAGS强制先包含原生成config.h，保持默认make目标和源码不变。在新工程身份`cpp-build-e58-failure-repair-v3`中验证两次真实恢复：补gtk-doc-tools，再补编译参数。v1及其中脚本回复耗尽的记录均保留；脚本回复耗尽产生的unknown_usage不是外部Provider未知账单，本轮实际Provider调用始终为0。中间v2输出为一次误启动的旧入口，编辑断言失败后被shell继续执行，已主动中断并清理，`interruption.json`明确登记，不用于成功或方法效果统计。

## 最终工程结果

| 项目 | 主构建 | 交付及轻量检查 | 原归档干净重建 | 原输入 | 最终路径耗时 |
|---|---|---|---|---|---:|
| smenu | 通过 | 通过，PTY版本入口 | 通过 | 未变 | 31.07秒 |
| quickjs | 通过 | 通过，算术表达式 | 通过 | 未变 | 84.83秒 |
| zstd | 通过 | 通过，原生版本入口 | 通过 | 未变 | 95.42秒 |
| libtasn1 | 通过，默认make全部目标 | 通过，主要静态库/共享库 | 通过 | 未变 | 274.37秒 |

前三项取v1独立工程运行，libtasn1取v3的新运行；表中时间只描述最终路径，不把保留的失败或中断删去后计算方法收益。libtasn1在v3中两次真实失败后分别提交预写补包方案和编译参数方案，最终main_build_task_completed及reproducible_delivery_completed均为true。全部作者测试不是本轮任务要求。

新清理命令原容器实际退出0，干净重建也通过；2400长路径的回归例确认命令小于2KB、原文件保留、生成物清除。补充检查覆盖普通reproducers文件名、真实/repro限制、清单篡改在删除前停止，以及重建清单对文件/目录链接/.git排除的一致性。51项针对性检查通过，Ruff和格式检查通过。局部合并运行测试时曾遇既有跨测试模块fixture收集顺序问题，按现有模块分别运行后全部通过，没有修改无关测试设施。

所有本轮构建/重建容器及中断路径的20个容器名称/ID引用均确认不存在。实际Provider调用0、费用0；v3的两条model_requests是预写脚本回复。工程修复阶段完成，未自动启动集中比较或改论文。

## 证据位置与下一阶段

- [四项目摘要与逐条失败命令](../../benchmarks/analyses/e58-failure-repair-2026-11-17/summary.json)，SHA-256：`6532dfb88e892c932701785a7cf3f98904308bb66d02bc3e5df721226823ada3`。
- [派生脚本](../../benchmarks/analyses/e58-failure-repair-2026-11-17/derive.py)、[新版本四项目参考](../../benchmarks/analyses/e58-failure-repair-2026-11-17/corrected-references.json)、[容器清理核验](../../benchmarks/analyses/e58-failure-repair-2026-11-17/verification.json)。参考可供下一批复用，原冻结fixture不变。
- 原件`/home/yiwei/.codex/outputs/forge-e58-failure-repair-2026-11-17-v1`：四条首轮工程路径、原方案和修正参考、实际失败、源码快照、session和构建/重建日志。
- 原件`/home/yiwei/.codex/outputs/forge-e58-failure-repair-2026-11-17-v2`：误启动的旧入口及中断记录，未用于效果统计。
- 原件`/home/yiwei/.codex/outputs/forge-e58-failure-repair-2026-11-17-v3`：libtasn1两次恢复、最终默认构建与交付、独立干净重建、清理及源码快照。

本轮支持“共同执行器阻断已修复、四项目存在可完整执行的正确构建路径”，不证明模型已自主学会新增编译参数。后续集中比较使用同一修复基座与正确独立参考，初始规划、恢复和失败全部重新计量；若修改Harness，先向用户展示修改内容再比较。保留E58原结果，不把本轮工程成功补成原实验成功率。

