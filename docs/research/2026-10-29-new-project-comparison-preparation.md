# 新项目系统比较：方法梳理与执行准备

日期：2026-10-29；[Issue #646](https://github.com/WWFXL/Forge-AutoCompiler/issues/646)。本阶段完成方法整理、任务准备和必要的人工参考运行，新增真实Provider调用与模型费用均为0，尚无本批方法效果结果。

## 这次补充哪项论文证据

E30在八个已开发任务上完成48次真实比较，Forge和强工具Agent均16/16完整，Forge估费低22.9%、累计时间低2.7%；不能据此推断新项目表现，也不能把系统收益全部归于配置直接动作。下一批固定当前方法，在未用于当前方法调试的项目上扩展完整比较；同初始方案的状态消融随后单独开展。

[当前方法说明](2026-10-29-state-action-method.md)已把实际架构、阶段观测、状态与动作选择和E30／E01／E04／分层验证联系起来。配置语义当前只覆盖显式CMake BOOL目标；依赖问题主要交给Agent，Make／Autotools仍走普通阶段Workflow。此处没有新增分类器、规则库或产物定位增强，也没有改动旧冻结方法。

## 新样本与真实参考观察

先登记八个候选及源码commit，再读取源码、定义原作者任务并做参考执行。仓库完整名称在基线指定跟踪目录均无命中；inja子串命中来自Ninja等词，FSE精确词命中是论文会议。检索范围与原命中保存在[selection.json](../../benchmarks/fixtures/new-project-comparison-v1/selection.json)，不证明全历史、训练未见或项目族独立；参考准备已暴露，不称完全盲holdout。

|项目|语言／系统|冻结的原作者任务与交付|准备观察与后续角色|
|---|---|---|---|
|jsoncpp 1.9.5|C++／CMake|全部3个CTest，原unit与readerwriter；`libjsoncpp.a`|两作业CTest出现共享输出文件竞争；全套串行-j1新参考3/3通过，原失败保留；主比较|
|PEGTL 3.2.8|C++／CMake|全部128个CTest及默认示例；交付原`pegtl-test-ascii_forty_two`程序|完整通过；主比较；header-only任务交付编译后的原测试程序，不称二进制库|
|inja v3.4.0|C++／CMake|全部2个CTest，各15 case／250 assertions，以及默认benchmark构建；交付`inja_test`与`single_inja_test`|完整通过，标准合并头生成后原文件字节相同；主比较|
|highwayhash 固定master提交|C++／Make|原highwayhash、vector、sip_hash三个测试程序；`libhighwayhash.a`|完整通过；主比较|
|libsigcplusplus 2.12.1|C++／Autotools|原make check的32个程序全部实际通过；`libsigc-2.0.a`|安装真实mm-common依赖、标准bootstrap后通过；主比较|
|libsrtp v2.5.0|C／Autotools|原make runtest的全部应用和嵌套crypto测试；`libsrtp2.a`|完整通过；主比较|
|FiniteStateEntropy 固定dev提交|C／Make|原make test：往返、fullbench及三个默认fuzzer，131072／32768／131072次；`fse`|完整通过；主比较，固定检查不缩减默认循环|
|libxcrypt v4.4.36|C／Autotools|原make check|初次缺libltdl-dev导致宏未定义，补依赖的新参考47 PASS＋1原生条件SKIP；保留为参考，不进主比较，不替补|

八候选的所有参考终态均保留，原文件内容均未改变、实际容器清理均成功。libxcrypt的宏错误来自缺少ltdl开发宏，**未证实是Libtool版本冲突**；探索下载的两个GNU工具包未加入正式源码归档或Agent输入。其`test/getrandom-fallbacks.c`在有arc4random_buf的平台明确返回77，因为该回退代码没有编入；不把这种不适用当作者测试报错，也不通过伪造HAVE_*或改测试制造48项实际通过。主比较保持本批全部固定原测试实际通过的口径，剩七项，不因新方法成绩换样。

jsoncpp的两个readerwriter原测试写同名`.actual`、`.actual-rewrite`等中间文件；并行参考日志记录交错执行及三个不稳定失败。随后新鲜构建的全套串行测试通过，故把`-j1`明确纳入三方共同固定任务。构建仍两作业，没有删减测试；后续不能把此条件差异解释为方法收益。

精确版本、原归档SHA、原作者声明摘录、全部检查命令、完整注册测试名称和交付见[tasks.json](../../benchmarks/fixtures/new-project-comparison-v1/tasks.json)。源码归档不含Git身份，由既有共同步骤建立索引；人工正确参考配方存于开发会话，不传入正式Agent。

## 可直接启动的比较

身份`cpp-build-new-project-system-comparison-flash-v1`，**七项目×两重复×三方法＝42次，每方法14次**。Forge、强工具Agent、CXXCrafter社区版及其全部运行组件、Flash low、资源、计费、恢复边界与E30相同；只替换样本和身份。强工具为主要对照；CXX保留原生工具／反馈／CPU约束差异，只作当前社区实现参考。六种方法顺序轮换，失败不替补，原源码／原测试／精确交付／完整同镜像重放保持。

- [新入口](../../scripts/forge_build_new_project_comparison.py)直接调用原三系统入口；分析分母按本批调度计算，不继承E30的16。
- [manifest](../../benchmarks/manifests/cpp-build-new-project-system-comparison-flash-v1.json)固定源码、任务、顺序与组件。
- [预注册](../../benchmarks/preregistrations/cpp-build-new-project-system-comparison-flash-v1.md)固定问题、比较条件、全部成本、分层分析及停止规则。

backend环境中运行`uv run python ../scripts/forge_build_new_project_comparison.py --check-prepared`可只读检查；正式执行沿原`--candidate`、`--authorization-root`、`--output-root`与共享费用账本，输出根必须不存在。当前候选SHA `2b88330c1e748b9fe43bd54dfb41941eacf929985492ba961dc5589c74aafef4`。

## 必要检查与证据位置

10项本次及相邻检查、Ruff及候选CLI通过，全部固定检查命令Shell语法通过；没有重复旧资格链或本地产品全测。七项交付均在参考构建树中观察到ELF/ar文件；这项存在性检查不代替正式精确交付及replay。

独立`cpp-build-new-project-task-check-v1`用人工脚本方案实际跑通inja新任务：两个原测试共30 case／500 assertions、benchmark、原文件／链接、两个程序精确交付、同镜像完整clean replay与cleanup全部通过。1个脚本响应、0真实Provider／Token／费用。原子runner继承`real_model_development_canary`类别字样，以本检查明确的脚本身份解释，不当真实模型成功率或新方法效果。构建与重放name／ID四项实际inspect均不存在。

版本化[准备分析](../../benchmarks/analyses/cpp-build-new-project-preparation-v1.json)保存全部参考结果、来源收据、脚本检查与各结果SHA。原始会话`/home/yiwei/.codex/outputs/forge-new-project-preparation-2026-10-29/`保存选样时点、上游归档／源码、各参考的完整日志和结果、jsoncpp／libxcrypt原失败及新参考、脚本任务执行、配置观测原字节和资源检查。阶段性质登记为论文实验设置／工程参考，不计模型效果数据。

## 下一项执行决策

建议为这42次比较授权新增模型费用上限10美元、确认起8小时；无自动重试，未知用量／模型身份异常／清理失败停止。窗口不足的余槽如实记未观察，不挪用E30旧授权或剩余额度。具体方法与任务已经可审查；确认后直接真实采集，不重复整批参考或三入口检查。

采集后先给固定42槽系统主表、项目／系统分层、初始与恢复成本和分层验证，再登记全部自然初始方案设计同方案三臂消融；不只选能修复的偏差。论文选材继续沿[E30／E01／E04及分层结果](THESIS_EVIDENCE_INDEX.md)，本阶段不替代它们，也不等待所有指标胜出才组织论文结果。
