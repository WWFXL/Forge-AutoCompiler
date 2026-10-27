# 当前Forge与CXXCrafter社区版：阶段性参考结果

Issue629；真实数据采集及结果分析。用户明确指定CXXCrafter对比只作当前版本参考，用于寻找系统增强空间；不以此裁定Forge最终能力或否定既有方向。沿用原新增模型累计10美元与UTC2026-10-27 12:44:30截止，无自动重试。

## 身份与观察完整性

第一身份原定三个已见项目×两策略六槽，simdutf两槽终结后因新槽需剩1800秒而停止，保持2观察/4未观察。第二身份在第一身份完整计量与清理终结后，前瞻固定原未观察的tinyxml2、check共四槽，新槽预留改900秒，其余任务与源码/测试标准不变。它不是续跑原身份或重跑simdutf失败；下面按身份分开保留分母，不称原六槽全部完成，不作跨批确认性效应。

| 身份 | 已观察/原计划 | 剩余未观察 | 停止原因 | 新增估费美元 |
| --- | ---: | ---: | --- | ---: |
| 原六槽参考 | 2/6 | 4 | remaining_time_or_budget | 0.2290020 |
| 独立短项目参考 | 4/4 | 0 | 全部槽终结 | 0.0900876 |

## 逐槽结果

| 身份 | 项目 | 策略 | 任务终态 | 请求 | 保守估费美元 | 总槽秒 |
| --- | --- | --- | --- | ---: | ---: | ---: |
| 原六槽 | simdutf | 模型规划Workflow＋失败Agent | 未完成，见失败分析 | 28 | 0.1955703 | 518.61 |
| 原六槽 | simdutf | CXXCrafter社区版 | 完整完成 | 6 | 0.0334317 | 763.92 |
| 独立四槽 | tinyxml2 | CXXCrafter社区版 | 完整完成 | 6 | 0.0127209 | 55.43 |
| 独立四槽 | tinyxml2 | 模型规划Workflow＋失败Agent | 时窗截断，重放未观察 | 2 | 0.0066777 | 18.30 |
| 独立四槽 | check | 模型规划Workflow＋失败Agent | 时窗截断，重放未观察 | 9 | 0.0547884 | 331.60 |
| 独立四槽 | check | CXXCrafter社区版 | 两次构建失败后时窗截断 | 5 | 0.0159006 | 249.23 |

表中非完成槽不统一解释为方法失败。Forge的原始strict_completed=false保留，但运行窗口拒绝属于删失观察，不能和恢复失败混为一类；未运行的重放不填通过或失败。费用包含失败、读取、初始规划、原生审阅/Judge以及全部恢复，不能只比较成功槽费用。

## simdutf：确实观察到的当前方法弱点

Forge初始方案读取过固定任务合同，但配置SIMDUTF_FAST_TESTS=ON、SIMDUTF_TOOLS=OFF；构建退出0，固定检查因FAST_TESTS要求不符而拒绝。第一修订改动配置并加入测试数必须为94的附加检查，build动作在该检查处退出1；第二修订再次使用FAST_TESTS=ON和TOOLS=OFF，并尝试动态发现测试目标，build动作仍退出1。三版、两次handoff、八个命令后触达原恢复边界；完整作者功能测试、精确交付和clean replay未观察。不能把固定配置检查失败写成原作者测试功能bug。

| Forge环节 | 请求 | 输入Token | 输出Token | 估费美元 |
| --- | ---: | ---: | ---: | ---: |
| 初始规划 | 9 | 115666 | 3517 | 0.0389202 |
| 恢复修订2 | 9 | 171830 | 13616 | 0.0678882 |
| 恢复修订3 | 10 | 212681 | 20798 | 0.0887619 |

CXXCrafter同项目一次Dockerfile正确设置FAST_TESTS=OFF、TOOLS=ON，原生六次模型请求后自报成功；外部原次与无缓存重建均94/94完整通过，源码/原索引保持，libsimdutf.a路径、类型、大小、SHA-256一致，任务容器和tag清理通过。原/重建完整测试分别235.63与231.79秒。该配对是当前实现上的真实反例，说明规划Workflow在此条件下可以反复偏离已经读到的要求；不支持“规划必然省钱”或仅凭更多读取就会更可靠。

## 运行窗口截断与可比性限制

第二身份缩短了外层新槽预留，却未同步Forge内部OperationWindow.replay(1200)加300秒清理的准入要求。tinyxml2已完成构建、原测试、精确暂存，但剩余不足1500秒时拒绝重放。原始记录不改，必须明确判作重放未观察。这是本次调度设计遗漏，不能归因于构建方法能力，也不能通过给它填“失败”制造CXXCrafter成功率优势。check的Forge也通过build、make check和精确交付后被同一重放预留截断。check的CXXCrafter第一版缺makeinfo，Modifier补texinfo后第二版因直接构建src而缺../lib/libcompat.la失败；再次请求前已不足900秒，0新增请求即停止。其完整测试/交付/重建均未观察，也属于恢复尚未终结的时窗截断，不能解释为给足窗口仍必然失败。

CXXCrafter使用当前可运行社区版src快照，含原工作树既有运行修复；上游main为bac70e99e48b210a350c18b3f93efd839787ce37，具体使用字节以manifest baseline.files为准。原目录及既有用户修改未改。此处不是CXXCrafter论文原版复现；保留原生Parser/CCScanner、文档选择/总结、Generator/Review、Docker构建、两级Judge及最多十版Modifier。统一deepseek-flash thinking low、固定基础镜像及两CPU。

任务义务语义相同，但呈现和反馈不完全一致：CXXCrafter生成提示直接附完整任务脚本，Forge较长脚本以SHA引用按需读取；simdutf三次规划实际共七次合同读取。原生Judge成功后外部测试失败不会再反馈基线修复，而Forge验证可触发handoff。CXX外部测试容器有2CPU配额，但固定test步骤执行未显式注入Forge的CTEST_PARALLEL_LEVEL=2；原生构建/外部测试/重建阶段与Forge阶段组织也不同。因此费用、时间和完成差异不能分离成纯规划/状态感知因果，尤其不能把失败或时窗截断的短耗时当作效率收益。

## 对论文与下一步的含义

本轮六个实际观察中，两项完整完成（CXXCrafter的simdutf/tinyxml2），一项方法未完成（Forge的simdutf），三项时窗截断（Forge的tinyxml2/check、CXXCrafter的check）。本轮新增的是可运行社区版的三类构建任务尝试及当前实现失败/截断证据，不是完成大规模公平系统排名。旧22槽完整策略比较和五对恢复消融保持原结论；本轮不会用工程失败否定主线，也不会用参考结果宣称系统已成熟。

下一步[Issue631](https://github.com/WWFXL/Forge-AutoCompiler/issues/631)优先做一项直接关联方法的增强：把显式任务义务整理成可持续核对的目标约束，观察配置状态、测试准备和产物目标覆盖，在configure后尽早识别与目标不符，恢复时保留已确定约束；未知依赖和复杂语义仍交Agent。先与当前版本做配对增量实验，检验是否减少无效重编译和反复规划，再扩大系统比较。它目前只是有失败证据支持的研究候选，不是已经证明的创新效果。

下一轮统一新槽、请求、命令和重放时间合同，在完整有效窗口前段执行；按项目参考时长预先声明合理的重放上限和清理余量，不在处理结果出来后改时限。保留全部原测试/源码/交付标准，避免再把窗口准入截断混入方法结果。

## 费用与证据

两项参考共56次模型请求，新增已知保守估费0.3190896美元；加此前22槽0.4366236美元，本轮累计0.7557132美元。输入全部按缓存未命中0.30/输出1.20美元/M估算，不是实际账单。未知用量及清理以各原始result/usage记录为准，禁止推定未知免费。独立分析逐个原始SDK/AI响应复算Token与费用并核对记录，两个typed inventory均只读通过。

本轮仅三项SDK计量/源码局部检查、Ruff和实际prepare，未重复全量本地产品检查。合并以最终HEAD三项CI实际通过为准。

- cpp-build-current-cxx-reference-flash-v1：raw `/home/yiwei/.codex/outputs/forge-cxx-current-reference-v1`；release `a26dbe21564012abeb5647e7ccaa1792a18e54e8`；inventory `f88f5ca0978887593b6c3600b7433965d73ffe509199d953b2aff50e686f287b`；版本化分析 `benchmarks/analyses/cpp-build-current-cxx-reference-flash-v1-results.json`。

- cpp-build-current-cxx-short-reference-flash-v1：raw `/home/yiwei/.codex/outputs/forge-cxx-short-reference-v1`；release `374b6198f823846d29aa8c58afee966b4a1e16e4`；inventory `52c32ed1a54bf3c50b2b46185efdba1657d26aedca90fd56ebd855befc3b9227`；版本化分析 `benchmarks/analyses/cpp-build-current-cxx-short-reference-flash-v1-results.json`。

授权、快照原状态、启动日志、两项独立分析和报告生成脚本保留在`/home/yiwei/.codex/outputs/forge-cxx-current-reference-session-2026-10-27`。原始证据不回写。
