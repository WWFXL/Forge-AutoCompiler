# libffi真实依赖与Agent兼容宏的当前平台功能对照

2026-11-16；Issue #770；类型：零Provider后验功能验证与结果分析。

## 结论

两条新构建的有效配置宏、公开头文件、共享导出与静态全局符号一致，五类实际调用在静态/动态链接下全部通过。上一轮Agent实际交付的原产物副本也通过相同探针。因此，补充证据支持将上一轮解释为**当前固定Linux x86_64环境下的成功构建与可复现交付**，而不是因其未采用最优依赖安装方式而否定成功。

原真实宏检测结果为`no`，恰好与Agent替代宏的固定值一致。这解释了为什么没有安装`libltdl-dev`也能得到有效的当前平台产物。它不修正Agent此前关于“新版移除宏”的错误诊断，固定值替代仍不具备原宏的跨平台检测能力。

## 比较如何进行

用户批准“下一项尝试”，按上一回复首项执行；身份`cpp-build-libffi-functional-comparison-v1`，[预注册](../../benchmarks/preregistrations/cpp-build-libffi-functional-comparison-v1.md)，[入口](../../scripts/forge_libffi_functional_comparison.py)，运行revision `76fc0fa7`。

复用固定libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`、归档SHA `d5dd45924e8cf71d72aac04e377d7f8bc5b4d6f76d53c75522742e707e6098cd`、不可变镜像`8123220a`；每路径一个独立空目录/容器，CPU2、内存4G、同一网络与国内HTTPS镜像。两条均执行作者autogen、`./configure --disable-docs`、`make -j2`。文档开关对齐，避免把是否构建文档误当宏差异。

- 真实依赖路径安装`libltdl-dev:amd64 2.4.7-7build1`，记录`/usr/share/aclocal/ltdl.m4`所属包与真实内容；Libtool仍为2.4.7，没有降级或自造宏。
- Agent宏路径只复制上一轮最终接受的`m4/lt_sys_symbol_uscore_compat.m4`，不安装上述包，没有模型重新规划或人工改良宏。
- 编译同一个[C探针](../../benchmarks/fixtures/libffi-functional-comparison-v1/probe.c)，分别链接各路径当前编译的静态库与共享库。动态链接记录实际库路径，排除误用系统libffi。
- 在Agent路径容器中，另用上一轮原始静态/共享交付库及公开头文件的只读副本编译相同探针。两库SHA与上一轮冻结summary完全相同；原证据目录未修改。

本轮不使用Provider、不读凭据、不改Agent；0Token、0美元。每路径一次，无非预期失败、无重试；共53.57秒，两个容器清理并按ID实查不存在。

## 结果

| 比较项 | 结果 |
|---|---|
| 真实宏下划线检测 | `lt_cv_sys_symbol_underscore=no` |
| Agent宏下划线结果 | 固定为`no`，当前值一致 |
| 有效fficonfig.h宏定义 | 40项，完全一致，无单侧差异 |
| 生成公开ffi.h与ffitarget.h | 内容一致 |
| 动态导出符号名称及类型 | 42项，一致 |
| 静态全局符号名称及类型 | 一致 |
| 新真实依赖产物，静态/动态 | 各5/5场景通过 |
| 新Agent宏产物，静态/动态 | 各5/5场景通过 |
| 上一自主运行实际产物，静态/动态 | 各5/5场景通过 |

五场景为：有符号整数调用、浮点调用、混合结构体传参/返回、变参调用、closure分配与回调。探针对照普通C直接调用或已知计算答案，检查ffi_prep返回状态及真实结果，不只是库文件存在或程序能启动。共6个程序、30个场景执行，不是30个项目或新增模型实验样本。

## 如何使用这个结果

上一轮已经观察到主构建、交付与原始归档干净重建通过，本轮再补充实际产物的配置/接口及代表性调用验证。当前任务目标是固定环境中的主要库构建，因此可以认定在这个目标下成功；无需把“必须找到某个指定包名”作为成功条件，也不要求两条产物逐字节一致。

成功不等于诊断正确或路径最优。真实宏根据编译器和符号工具探测当前环境；替代宏直接假定`no`。其他目标平台或ABI下该假定可能不成立，不能将它作为通用缺依赖修复经验。若保存为同项目精确复用，应保留当前commit/镜像/架构及新增宏说明，不自动扩展为跨平台知识。

前轮原件中的`source_review=pending_review`与原报告是当时观察，保持不改。本次新增后验评估给出“当前平台功能验证通过”，不是回写原实验或新增独立项目分母。没有跑完整作者测试，也没有证明所有调用约定等价；本轮完成了事先约定的有限功能判断，不继续追加资格或全量测试。论文不自动修改，先交用户审核。

下一研究工作仍应围绕依赖提供者诊断：索引覆盖、文件提供者查询与推理过早收敛。本次不实施工具改动或付费新项目比较，避免将功能核验与下一处理混在一起。

## 证据

- [摘要](../../benchmarks/analyses/libffi-functional-comparison-2026-11-16/summary.json)、[原产物与诊断核验](../../benchmarks/analyses/libffi-functional-comparison-2026-11-16/verification.json)、[封存](../../benchmarks/analyses/libffi-functional-comparison-2026-11-16/seal.json)。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-functional-comparison-2026-11-16-v1`，含scope、命令/退出码/耗时、两条实际构建及全部日志、包清单、真实宏、配置、符号、探针源码/程序/输出、原产物副本及清理记录。
- inventory SHA：`d70334fb773bc5508aa353f0e9fab1c6c3a40f32890182dc2f7d5cc235b69ac4`；1340普通文件、12链接。脚本及C探针的运行快照保留。
- 上一轮：[后验审查下libffi自主构建](2026-11-16-libffi-posthoc-review-autonomous.md)。本次与其重叠，不合并或替换原统计。
