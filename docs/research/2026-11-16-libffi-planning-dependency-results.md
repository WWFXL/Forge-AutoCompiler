# 规划依赖检查的libffi自主观察结果

2026-11-16；Issue #801。真实数据采集与结果分析，结果先交用户审核，不写论文。

## 结果与执行路径

本次没有完成构建：规划Agent实际调用了新增依赖查询，但未提前识别缺失宏；恢复Agent查到缺失开发包后，在提交修订方案前被本地上下文容量限制停止。不是安装失败、预算不足或Provider报错。

1. 初始规划共7次Flash请求，实际执行10次只读查询：项目中搜索autogen.sh；核实autoconf、automake、libtoolize、autoreconf、makeinfo、gcc、make及pkg-config；搜索makeinfo引用。它确认主要工具存在、文档工具缺失，根据作者说明选择`--disable-docs`，没有查询宏定义是否齐全，也未生成依赖安装步骤。
2. 首份方案为`./autogen.sh && ./configure --disable-docs`，随后`make -j2`。第一步因`LT_SYS_SYMBOL_USCORE`未定义退出1；`configure`和`make`尚未成功执行。Workflow正确转交恢复，不是成功命令被误判。
3. 恢复前原诊断流程自动做3查询。第8次模型请求是唯一恢复请求：系统提示已包含审核经验；Agent调用`diagnose_dependency(kind="macro", item="LT_SYS_SYMBOL_USCORE", component="libtool", candidate="libltdl-dev")`，并额外调用一次`package_files`。组合查询实际核实包描述、未安装状态、已装文件列表和aclocal路径，共5次主动子查询。未安装包的`package_files`返回无法列文件，属于真实环境反馈，不表示工具不可用。
4. 这些结果产生后，下一次请求的本地上下文装配抛出`PlanContractError: 公开任务与压缩后的必要证据超过规划上下文容量`。账本保存`context-request-9-group-1.json`及压缩事件，但没有第9次Provider请求或响应，没有第二份方案、依赖安装或后续构建。
5. 任务失败保留，主库、交付和干净重建均未观察。原输入保持不变，17项生成文件新增；语义后审为pending_review。主容器清理成功，名称/ID均实际核实不存在，没有创建重建尝试。

## 开销

| 阶段 | 请求 | 输入Token | 输出Token | 美元 |
|---|---:|---:|---:|---:|
| 初始规划 | 7 | 89134 | 2326 | 0.0295314 |
| 恢复 | 1 | 12879 | 271 | 0.0041889 |
| 合计 | 8 | 102013 | 2597 | 0.0337203 |

总Token104610，耗时35.66秒，未知用量0。实际规划查询10次、恢复查询8次（自动3/主动5），共18次；单次查询及执行计原任务额度。费用少是因为提前停止，不能解释为效率改善。上一宏经验观察11请求/0.0432美元/85.55秒并完成，本次没有完成，不能直接按费用排序。

## 原因与意义

新增能力已实际送达并使用，但本例的初始检查停留在工具存在性和版本层面，尚未从构建声明深入到宏提供者。工具可查不等于规划一定会选择关键查询。只检查libtoolize存在不能证明所有Libtool相关宏都已安装。

恢复阶段已经采用经验并主动核实候选，最终停止来自共同上下文管理：`simple_planning_context.py`对消息正文加系统提示设置49000字节本地上限；移出初始源码片段、压缩交接和最近AI/工具组后仍超限便停止。新增诊断结果同时进入对话、任务内证据记录等载体，组合装配未能在当前上限内保留下一次修订所需上下文。本次未发送的第9次完整请求未保存，不报告其精确字节数，也不能归因于模型服务端上下文窗口。

支持的结论是：规划查询接线有效；本例未观察到关键依赖提前发现；恢复能主动核实经验中的候选；共同上下文装配阻断了修订。下一步优先对现有失败材料做零Provider复现，缩减重复诊断表示并保留失败事实、候选、核实结果及原件指针；不是继续增加提示或查询额度。本轮不修改执行器，不自动重跑。

## 设置、授权与证据

身份`cpp-build-libffi-planning-dependency-flash-v1`；运行revision `0700a261cfb16b24b7bd4dfdb0bd05af8d16ebcc`，PR800入口。用户明确授权一次/1美元硬上限/确认起1小时，无自动重试；记录UTC15:00:43—16:00:43，唯一会话UTC15:01:24—15:01:59。全部费用计入，本次授权的一次运行已经使用，不用余额追加。

仅新增规划真实容器查询与通用依赖指导；P0初始系统提示不包含宏依赖经验或具体包名，恢复沿用已审核9de184d7经验。固定libffi原归档、d483ffa7查询镜像、Flash thinking low、Workflow和主构建目标；不提供旧成功指令，不动态检索个人知识库。属于已暴露开发案例，不增加独立项目分母，不回填E57。

- [分析及逐请求轨迹](../../benchmarks/analyses/libffi-planning-dependency-2026-11-16/analysis.json)、[18次实际查询](../../benchmarks/analyses/libffi-planning-dependency-2026-11-16/queries.json)、[提示/计费/快照/清理核验](../../benchmarks/analyses/libffi-planning-dependency-2026-11-16/verification.json)、[原件清单](../../benchmarks/analyses/libffi-planning-dependency-2026-11-16/inventory.json)。派生分析仅消费原件，未发模型请求。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-planning-dependency-flash-2026-11-16-v1`，616文件；inventory SHA-256 `e1fdca09a62e2f79b3c997740443f6e1834dca73645f91c9b6396ad4881a3e75`。
- 86份源快照、8次响应模型、逐响应费用及Token、初始/恢复提示区分、两个容器引用不存在均核验通过。失败与全部查询保留，无自动重试、追加或论文修改。
