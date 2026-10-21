# 五个C++候选的完整根源码与任务合同审阅

Issue #579。阶段为只读数据采集、静态合同分析及版本解析工程修复。目的：把原固定30项中的定义队列9/10/14/21/30推进到可冻结参考构建的具体义务，不按三策略效果选样。本轮没有执行上游构建或付费Provider。

## 结果与边界

五项全部尝试，四份根归档与完整Git树一致，Yosys一份归档失败，零未观察。独立标准库清单和真实`git mktree/hash-object`核验503个树、7003个归档blob及权限/路径；Yosys的失败差异被保留，审计valid不等于五项来源全通过。全部`task_qualified=false`、`contract_complete=false`、`build_result=not_observed`、非holdout；根源码可核验不代表外部依赖、测试、交付或重放已闭合。

[逐项义务及49处原文引用](../../benchmarks/analyses/cpp-build-prospective-task-contract-sources-v1-results.json)记录固定commit、路径、行号、原文、Git blob SHA、文件SHA256及归档是否匹配。Yosys `.gitcommit`明确标为不匹配诊断，不能当Git原blob引用。其余引用均逐文件检查了Git对象身份。引用只是静态事实，不是已执行结果。

| 原排名 / 项目 | 当前新增事实 | 参考运行前仍须完成 |
| --- | --- | --- |
| 9 ArrayFire | `afcpu`真实库与后端测试注册；存在main/master及短ref外部源 | 冻结CPU/unified范围、全部源码/数据与系统包、完整作者测试、资源及交付集合 |
| 10 rtorrent | 同版本libtorrent根来源已核验；Core/Rpc/Src三测试程序及CppUnit断言退出码明确 | 依赖完整图、系统包/宏、测试分母、任务专属B生成关系、精确交付与实际参考/replay |
| 14 Dobby | 仿真测试包含树内不存在的头路径；native含dyld/_execve假设；构建版本含日期 | 不改源码/测试解决来源与平台合同；Clang Blocks、Capstone/Unicorn、全原测试与时间输入 |
| 21 Yosys | codeload对`.gitcommit`做export-subst；另有8个未闭合gitlink | 新身份取得canonical Git原对象/归档及子模块，再闭合原完整测试与工具链 |
| 30 IWYU | 0.28主干跟随Clang主干；CTest/Python存在prerequisite skip/expected-fail | 精确LLVM/Clang/资源目录与全部测试范围、资源预算、精确交付与重放 |

这五项是封存后定义工作队列，尚不是最终比较样本；其他25项仍pending，无替换或补位。Dobby缺路径是静态障碍，不能填作真实编译失败或全项目不可编译。ArrayFire不能为减少失败而事后关闭原测试；IWYU exit77不能填作断言通过。Yosys不因差异可解释而回改v1结果或放宽已冻结校验。

## rtorrent同版本依赖及解析失败

rtorrent README要求同版本libtorrent，主项目configure版本0.16.25。独立`cpp-build-rtorrent-dependency-source-v1`只查询一次默认分支并冻结ref→commit→tree，再取精确归档：

- 仓库：`rakshasa/libtorrent`，master，commit `c395f0af3924bb4c8514cfa3b0c46c78787ddc64`。
- 根tree：`7d0d5fa1a7784a6a6c10008647b33df7c1852375`；归档SHA256：`041c71d60632a988dbddc72c849b74a4879697065a192a0b517e3df3394c47eb`。
- 实际首行：`AC_INIT([[libtorrent]],[[0.16.25]],[[sundell.software@gmail.com]])`。

v1归档/树核验后，版本正则不接受合法双层M4引用，封存`source_qualified=false`和错误消息“不是所需精确版本”。该消息是工程解析误拒，**不是上游版本不匹配的证据**。v1不重跑、不修改，亦没有选择另一commit或版本。

修复以独立`cpp-build-rtorrent-dependency-recheck-v2`运行，组件及协议先测试/提交，再只读复核v1已下载材料，零新增网络。支持平衡的无引用/单层/双层M4参数，仍严格检查真实行首声明、项目libtorrent和精确0.16.25；注释、非平衡引用、其他项目及近似版本拒绝。v2根来源通过，但`dependency_graph_complete=false`，完整任务仍不合格。另一份不导入解析器的独立审计以实际首行字节、Git ref/commit/tree链、40树及493 blob、权限、清单和冻结release检查通过。

## 下一参考任务

优先继续rtorrent，原因是同版本来源已闭合且三个原测试程序有明确断言入口；并非已知方法优势。应先冻结libtorrent与rtorrent的完整系统依赖、原测试集合、工具链/镜像、时限、功能配置、精确产物及标准Autotools生成路径/命令/输出，再以新独立零Provider参考身份执行完整构建、原测试、源码保护、交付、同镜像clean replay及cleanup。不能缺CppUnit后空测试通过，不能用TEST_NAME过滤原分母，不能套用已见libconfig生成白名单。

本轮没有冻结或执行参考命令，不宣告自然恢复率、方法成功率、规划收益或总体排名。用户B决定继续适用：正常声明的生成文件可写，作者源码、原测试和构建语义输入受保护；不重复索要该决定。材料属于开发助手暴露，不自动注入实验Agent，不声称训练/历史未见。旧libconfig九槽、RQ3分母、P2、主线与用户HTML保持。

## 证据与核验

- 根来源raw：`/home/yiwei/.codex/outputs/forge-prospective-task-contract-sources-v1/`，inventory `4e439bbc667c7c6e48fc5026678b20fe96fc29fc7c9d4d52fe492b1d7474dbbc`，运行release `d57645673f2f6bfd37d91017dca3686c4645bab4`。
- 依赖v1 raw：`/home/yiwei/.codex/outputs/forge-rtorrent-dependency-source-v1/`，inventory `0e7296144f4a3ae8f3b79791ea88d6d476d188c44bd4429dcb096501f65d03b8`，运行release `d4967577`。
- 依赖v2 raw：`/home/yiwei/.codex/outputs/forge-rtorrent-dependency-recheck-v2/`，inventory `a1bf9d7a6997f0fde9d39f7bb0aab0efbcbd01d7182c82bb0bcd3ce455ee2a1c`，运行release `c151bd7e`；各身份完整组件SHA及运行源码快照见raw。
- 三份同名manifest/preregistration均在`benchmarks/`，不覆盖旧身份。
- 会话审计实现、独立结果、派生分析脚本、检查、发布及知识库CAS收据：`/home/yiwei/.codex/outputs/forge-task-contract-session-2026-10-21/`。

新增26项针对性测试通过，最终后端产品2348 passed、44 skipped、27 warnings；历史pytest临时目录权限清理告警保留。工程调用曾在根目录执行make test-product而因目标不存在退出，改用正式backend入口后成功，未影响采集身份。Ruff及格式检查须通过，结果HEAD三个相关CI后仅合科研依赖分支`yiwei/534-rq3-natural-failures`，不进入main，发布事实以GitHub和会话收据为准。没有前端变更，当前无pnpm，未安装或执行前端检查。

本轮0Provider、0模型凭据、0Token、0模型费用、0上游构建/容器执行；Docker只做运行时和镜像可用性只读检查。原免费来源窗口截止UTC2026-10-21T05:26:06.280620，不静默延长，不续用过期付费授权；未来付费比较须新有效预算/时窗。
