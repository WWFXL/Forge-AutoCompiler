# 已审核宏依赖经验辅助的libffi单次观察结果

2026-11-16；Issue #795；真实数据采集与结果分析。结果先交用户审核，未写入论文。

## 结果与实际路径

本次Agent核实并安装了真实开发包`libltdl-dev`，完成主库、静态/共享库交付、原归档干净重建及清理。共11次deepseek-flash请求、136293 Token，保守估费**0.0432美元**，总耗时**85.55秒**，未知用量0。

1. P0初始规划经过9次请求，读取autogen.sh、CI、Makefile.am及README，给出`./autogen.sh`→`./configure --disable-docs`→`make -j2`。`./autogen.sh`实际因`LT_SYS_SYMBOL_USCORE`未定义退出1。初始规划没有收到新增经验。
2. 首次恢复前原诊断流程自动查询本地宏、项目引用及libtool包描述，共3次；已审核的宏→文件→依赖经验只在恢复第10、11次请求送达。
3. 恢复第一次请求主动调用两项工具：`inspect_build_environment(kind="package", query="libltdl-dev")`确认未安装；`inspect_build_environment(kind="package_file_search", query="ltdl.m4")`返回`libltdl-dev: /usr/share/aclocal/ltdl.m4`。没有调用组合`diagnose_dependency`，但利用已有底层查询完成了核实。
4. 恢复第二次请求提交修订方案：`apt-get install -y --no-install-recommends libltdl-dev`，然后重跑原autogen/configure/build。包安装日志确认`libltdl-dev:amd64 2.4.7-7build1`与`libltdl7`安装成功。各阶段退出0，未源码安装其他版本Libtool，未自建替代宏或固定检测值。
5. Workflow精确交付库文件，独立新容器从原归档执行成功重建，重建约22.28秒。主容器与重建容器均清理成功，名称/ID四项实查不存在，付费进程已退出。

原输入保持不变，新增186项生成文件；运行记录的文件语义后审状态仍为`pending_review`。作者完整测试不属于本次主要库构建目标，未执行。

## 请求与费用

| 阶段 | 请求 | 输入Token | 输出Token | 美元 |
|---|---:|---:|---:|---:|
| 初始规划 | 9 | 106733 | 1740 | 0.0341079 |
| 恢复 | 2 | 26991 | 829 | 0.0090921 |
| 合计 | 11 | 133724 | 2569 | 0.0432 |

实际诊断查询5次：自动3次、Agent主动2次。单次失败恢复后完成，主库在约58.87秒完成，全部阶段含清理85.55秒。

上一无具体关联经验的观察为初始3/恢复8，共11请求、0.0652518美元、162.16秒；本次初始9/恢复2，共11请求、0.0432美元、85.55秒。恢复阶段费用从0.0522717降至0.0090921美元，执行路径从固定兼容宏转为真实依赖修复。初始规划增加来自本次多轮仓库/README读取，新增经验未发送给P0。总请求数没有下降，不将独立初始规划波动混同恢复效果。

本例支持“明确且有适用范围的错误经验可以被Agent核实并采用”；不再只是看到候选而忽略。它是经验来源项目上的利用观察，初始方案和读取过程也不同，因此历史开销差是描述性结果，不作为跨项目或稳定降本的因果结论。

## 设置与授权

身份`cpp-build-libffi-macro-experience-flash-v1`，用户在暂缓后明确“授权运行”，本次沿用所询问的一次/1美元硬上限/确认起1小时/无自动重试，保守记录UTC11:25—12:25；唯一运行UTC约11:28—11:30，位于有效窗内。不续用余额追加调用。

运行revision `df39303e95deba7fbe6107a8b37a5fce512c5481`（PR #794入口），候选`9de184d72f39866fd832a985f720293d6432ccd7c8a033e94f81f2376d4836d8`。仅恢复提示相对原R2诊断顺序组合追加已审核782字节经验，明确提供包名；P0、模型、工具、Workflow、额度及验收沿用。libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`及查询镜像d483ffa7保持。不提供旧成功方案，不动态检索个人知识库。

## 证据与下一步

- [逐阶段分析及完整命令](../../benchmarks/analyses/libffi-macro-experience-2026-11-16/analysis.json)、[五次实际查询](../../benchmarks/analyses/libffi-macro-experience-2026-11-16/queries.json)、[提示送达/计费/快照/容器核验](../../benchmarks/analyses/libffi-macro-experience-2026-11-16/verification.json)、[原件内容清单](../../benchmarks/analyses/libffi-macro-experience-2026-11-16/inventory.json)。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-macro-experience-flash-2026-11-16-v1`，1442文件；inventory SHA-256 `4c21279adadf9be149585ae98334f8c1f847a6f062bbabb6d6593414672e2fbf`。85份运行源快照核对通过；全部11响应模型标识正确，逐响应费用复算与账本一致。
- 同已暴露项目开发案例，不回填E57、不增加独立项目分母、不自动入文；所有历史失败保留。

本轮结束。建议用户审核后，将这条经验保留为通用错误经验候选，下一步以其他项目/依赖缺口检验其适用性，同时区分已有项目成功指令复用与新项目错误经验指导。是否开展下一比较由用户决定，本次不新增模型调用或继续修改系统。
