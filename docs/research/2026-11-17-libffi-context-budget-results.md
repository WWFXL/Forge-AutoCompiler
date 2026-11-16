# 上下文容量修复后libffi自主构建结果

## 本轮结论

一次从零自主运行完成了libffi主库构建、静态/共享库交付、原归档干净重建和清理。恢复Agent核实缺包和宏文件归属，提交安装`libltdl-dev`的修订，随后原`./autogen.sh && ./configure`及`make -j2`通过。本次没有再发生本地49KB上下文中断。

规划阶段仍未识别宏依赖：它安排安装文档工具`texinfo`后直接执行生成与配置，首次`autogen`依旧因`LT_SYS_SYMBOL_USCORE`未定义退出1。本次成功发生在恢复阶段，并非前置依赖规划已完善。

## 身份与条件

身份`cpp-build-libffi-context-budget-flash-v1`，[协议](../../benchmarks/preregistrations/cpp-build-libffi-context-budget-flash-v1.md)。用户在明确的一次/1美元/1小时建议后回复“开始执行”，本轮时窗为北京时间2026-11-17 00:12:23—01:12:23，准备计入。无自动重试或追加观察。

运行revision `a459eafd`，采用PR804容量修复后的共同底座；libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`、原归档`d5dd4592…`及查询镜像`d483ffa7…`不变。模型为deepseek-flash thinking low，P0规划可只读查询容器依赖；恢复使用已审核R2宏依赖经验`9de184d7…`。没有提供完整成功命令、初始方案或经验库；具体宏→文件→包关联只在恢复提示中提供。

相对前轮`cpp-build-libffi-planning-dependency-flash-v1`，共同底座改为64K输入工作预算、32768输出预留及精简诊断快照；旧失败原件完整保留。本例为已暴露的开发案例，不是独立新项目评价，结果先交用户审核，不自动入论文。

## 执行轨迹

| 环节 | 实际行为与结果 |
|---|---|
| 初始规划 | 8次模型请求、10条依赖查询；识别makeinfo/texinfo缺失，生成安装texinfo、autogen/configure、make方案 |
| 首次执行 | texinfo安装成功；autogen因`configure.ac:219`的`LT_SYS_SYMBOL_USCORE`未定义失败 |
| 恢复第1次请求 | 调用`diagnose_dependency`核实libltdl组件及候选包，并查询包安装状态 |
| 恢复第2次请求 | 用`package_file_search`查询`ltdl.m4`，返回libltdl-dev提供`/usr/share/aclocal/ltdl.m4`的证据 |
| 恢复第3、4次请求 | 补读configure.ac第1行和第200行起的内容，核实构建声明与宏调用 |
| 恢复第5次请求 | 提交完整修订，在原配置步骤前新增安装libltdl-dev；共9条恢复环境查询（含自动查询） |
| Workflow执行 | 重置本次生成物、安装libltdl-dev、原autogen/configure、make均通过 |
| 交付与重建 | libffi.a、libffi.so.8、libffi.so.8.1.4类型/非空检查通过；全新容器从原归档运行成功配方，干净重建通过 |
| 清理与文件记录 | 原容器及重建容器清理成功，四个ID/名称引用均不存在；原输入保持，新增187项留待后审 |

本任务为主构建，完整作者测试未要求，`full_completed=null`；不能据此声称完整测试套件通过。

## 用量与上下文

| 指标 | 结果 |
|---|---:|
| 模型请求 | 13：初始8、恢复5 |
| 累计输入/输出Token | 343,706／6,326 |
| 累计总Token | 350,032 |
| 全部模型费用 | 0.110703美元 |
| 运行总耗时 | 120.43秒 |
| 主构建完成时间（从运行开始） | 90.28秒 |
| 干净重建阶段 | 25.76秒 |
| 最大单次Provider实际输入 | 42,740 Token |
| 最大单次本地含余量输入预算 | 62,187／64,000 Token |
| 未知用量 | 0 |

累计35万Token包含每次请求重复发送的上下文，不是单次窗口占用。所有请求都在当前工作预算内；实际Provider输入与本地保守估算分别保存。费用按输入0.30美元/百万Token、输出1.20美元/百万Token逐响应核算。

此次完成了旧观察中未能继续的恢复与后续构建，但两次独立采样的读取、初始方案及执行路径不同，不能把费用或时间差解释为容量修复的因果收益。旧运行提前停止，其较少费用不代表同等完成更省。

## 证据与下一步

- [分析](../../benchmarks/analyses/libffi-context-budget-2026-11-17/analysis.json)、[完整查询](../../benchmarks/analyses/libffi-context-budget-2026-11-17/queries.json)、[上下文预算](../../benchmarks/analyses/libffi-context-budget-2026-11-17/context-budgets.json)、[核验](../../benchmarks/analyses/libffi-context-budget-2026-11-17/verification.json)、[原件清单](../../benchmarks/analyses/libffi-context-budget-2026-11-17/inventory.json)。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-context-budget-flash-2026-11-17-v1`。完整请求/响应、初始与恢复方案、执行日志、产物和重建配方均保留。
- inventory SHA-256：`4638cce766cc19e4097ba8554959efaafcf6234e6c9e24b731c78531ecd43685`。88个源码快照哈希、13次响应身份/用量/费用、经验仅在恢复送达及清理引用核验通过。

本阶段结束，无活动Provider。下一步建议结束围绕同一libffi的反复调试，先审核本例，再选择不同项目的依赖缺口，观察经验指导和前置依赖检查的适用范围；新增比较须单独确定范围。论文和E57现有结果保持。
