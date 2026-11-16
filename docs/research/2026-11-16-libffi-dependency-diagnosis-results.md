# libffi依赖诊断动作改进：单次自主构建结果

2026-11-16；Issue #789；真实数据采集与结果分析，结果先交用户审核，不写入论文。

## 结果

本次完成主库构建、静态与共享库交付、原归档干净重建及清理。11次Flash请求、165621记录Token，保守估费 **0.0652518美元**，总耗时 **162.16秒**，未知用量0。初始规划3请求，恢复8请求，仅一次失败恢复。

依赖诊断目标仍未达到。新流程在首次恢复前自动查到包含`libltdl-dev`的候选，并在第4—11次实际请求中持续提供；Agent没有核实它，而是继续搜索本地宏与项目，最终自行添加固定`sys_symbol_underscore=no`的兼容宏。构建通过与正确依赖诊断是本次两个不同的观察结果。

## 实验设置

身份`cpp-build-libffi-dependency-diagnosis-flash-v1`，用户批准1美元硬上限、UTC2026-11-16 10:42:38—11:42:38，一次从零自主构建，无Provider或整次自动重试。运行revision `64bf7b79a748ada2f6e8e78ce4c2913a8f5a0968`；入口来自PR #788。实际唯一运行在授权内结束，不续用余额追加观察。

沿用原libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`、原归档、查询镜像d483ffa7、P0及初始工具约束、规则路由、R2及诊断顺序指导、主构建验收和文件后审；开启已实现的依赖缺口诊断与证据记录。没有提供具体包名、旧成功方案或经验库。全部响应标识`deepseek-flash`，逐响应Token及费用与账本复算一致。

## 实际路径

1. 初始Agent读取构建说明，提出安装Autotools→`./autogen.sh`→`./configure --disable-docs`→`make -j2`。生成配置时实际出现`LT_SYS_SYMBOL_USCORE`未定义，退出1。
2. 自动诊断按日志识别宏缺口；查询已安装宏、项目引用及`libtool`包名/描述。第三项查询返回`libltdl-dev`等候选。组件名来自公开宏命名惯例，不是硬编码开发包答案。
3. 恢复Agent仍围绕`USCORE`及`LT_SYS_SYMBOL`搜索项目、宏目录与依赖目录，并查看已安装`libtool`文件；没有调用`diagnose_dependency`，也没有查询候选包精确描述或文件提供者。12条实际诊断查询中，3条为自动查询，9条由Agent发起；随后一次查询遭原交接额度拒绝。
4. Agent错误推断新版Libtool不再提供宏，新增`m4/libtool-usc-macro-compat.m4`，其中定义`AC_DEFUN([LT_SYS_SYMBOL_USCORE], [sys_symbol_underscore=no])`。Workflow执行修订后主库成功，独立干净重建同样通过。没有安装旧版Libtool，也没有安装`libltdl-dev`。

12条实际查询包括宏目录4、项目4、依赖目录2、包名/描述搜索1、已安装包文件1。第4—11请求的候选核实字段始终为空；实际请求文件确认候选都已送达。因此这次问题发生在候选核实与下一动作选择，不能解释为工具没有返回候选或上下文压缩丢失候选。

## 开销与结果解释

| 阶段 | 请求 | 输入Token | 输出Token | 美元 |
|---|---:|---:|---:|---:|
| 初始规划 | 3 | 34559 | 2177 | 0.0129801 |
| 恢复 | 8 | 113767 | 15118 | 0.0522717 |
| 合计 | 11 | 148326 | 17295 | 0.0652518 |

主库在约134.87秒完成，干净重建约22.93秒，总耗时含清理162.16秒。作者完整测试不属于本任务要求，未执行；库产物没有可执行程序smoke要求。原输入内容保持，新增187项文件，后验审查状态仍为`pending_review`。

实际生成的configure直接赋值`sys_symbol_underscore=no`，当前构建的`SYMBOL_UNDERSCORE`未定义。此前#770已对另一条固定宏路径做过当前平台功能验证；本次没有重做该功能实验，不将旧验证自动当作当前新文件的语义批准。当前主库及重建通过可以报告，通用检测语义等价及跨平台正确性尚不能报告。

与上一单次未完成的50请求观察相比，本次11请求并完成交付，描述性投入明显较少。但独立初始方案不同、同项目多次暴露，不能把全部差额归因新机制，也不能据此宣称依赖诊断成功或总体降本。

## 下一步

本轮停止，不追加修复或付费重跑。建议用户审核后，把下一项诊断动作改进集中到“已有候选但未核实”的分支：先核实少量候选的开发文件与缺口关联，再决定安装、路径修正或版本替换；避免继续重复本地搜索。这是待讨论设计，不在本次结果中实现。完成该机制后优先用不同依赖缺口及新项目检验，不再依赖libffi单例判断泛化。

## 证据

- [逐阶段分析与失败命令](../../benchmarks/analyses/libffi-dependency-diagnosis-2026-11-16/analysis.json)、[实际查询](../../benchmarks/analyses/libffi-dependency-diagnosis-2026-11-16/queries.json)、[候选送达与核实状态核验](../../benchmarks/analyses/libffi-dependency-diagnosis-2026-11-16/verification.json)、[原件内容清单](../../benchmarks/analyses/libffi-dependency-diagnosis-2026-11-16/inventory.json)。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-dependency-diagnosis-flash-2026-11-16-v1`。1466文件内容清单SHA-256：`b28416ae0e9da8bedd1bb1dff09dca0f52ace68050c1827b6583295e8c9bf7d1`，83份源快照核对通过。
- 授权及运行日志：`/home/yiwei/.codex/outputs/forge-dependency-diagnosis-session-2026-11-16-v1`。主容器与重建容器的名称、ID四项实际检查均不存在，无活动Provider。
- 同已暴露项目开发案例，不回填E57、不增加独立项目分母，原失败及论文保持。
