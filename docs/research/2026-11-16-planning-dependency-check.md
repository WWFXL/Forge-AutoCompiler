# 规划阶段依赖检查：实现与工程验证

2026-11-16；Issue #797。工程修复阶段，移除初始规划无法核实编译环境的限制，为后续研究“前置依赖检查能否减少恢复”提供执行能力。本轮不调用付费模型，不修改论文。

## 设计

规划职责由“只读取源码、生成动作”补强为“从作者文档/CI/构建声明识别依赖，查询实际环境缺口，生成安装动作及后续构建方案”。查询只读，安装仍由Workflow执行。

`PlanningEnvironment`复用现有固定查询程序及两项结构化工具：`search_build_files`、`inspect_build_environment`。可查项目/已安装宏/头文件/pkgconfig，工具版本、包状态、包描述、文件提供者及路径；没有新引入依赖库、任意Shell接口或新Agent。恢复原有组合诊断及交接范围保持。

新规划指导强调按明确线索核实缺包/路径/版本，将必要安装写入dependency步骤；不为可选示例或完整测试增加要求，不机械遍历全部依赖，不从本地空结果推断版本移除了功能。指导不包含libffi、宏名或包名答案。既有`PlanningHarness`及经验上下文仍可与该能力组合；本轮没有自动加入特定错误经验到规划提示。

显式配置`run_simple_system(inspect_planning_dependencies=True)`；CLI为`--inspect-planning-dependencies`。旧入口默认关闭，避免改变历史实验条件；下一模型观察必须使用独立身份记录开启。成功指令复用或固定初始方案跳过规划，不额外查询。

查询绑定初始规划的源码与会话，结束后关闭；最多12条、每条沿用15秒/文件提供者25秒执行上限，计入原64命令及任务时间额度。Workflow继承已用查询数，诊断命令不进入重建配方。没有构造失败或虚假恢复交接来开放工具。

## 验证结果

26项相关检查通过，覆盖真实Agent图反馈、初始查询到Workflow执行、额度、失效范围及既有恢复/已审核宏经验入口。Ruff和格式检查通过；未重复全产品本地测试。开发中首次缺Path导入及测试夹具断言/交接材料不完整已修正，正式工程构建只执行一次。

零Provider身份`cpp-build-planning-dependency-engineering-v1`，使用原libffi源码及d483ffa7查询镜像，预写4个Agent回复：项目宏引用查询→包安装状态→ltdl.m4提供者→提交依赖安装/原构建步骤。脚本明确给定libltdl-dev作为工程夹具，不是模型自主发现。

实际3次查询确认未安装及提供文件，然后安装开发包，执行`./autogen.sh`、`./configure --disable-docs`、`make -j2`。主库、静态共享交付、原归档真实干净重建及清理通过，没有任何恢复Agent交接，总耗时56.03秒。原输入不变，186新增文件后审。查询3＋执行4＝7，Workflow与meter命令计数一致；后续交付命令另由原验收处理。

76份运行源码快照核验与当前实现一致，主/重建容器名称和ID四项实际检查均不存在。0真实Provider、0Token、0新增美元；4次脚本模型消息不是模型效果请求分母。

## 结论与下一步

已证明初始规划能取得真实依赖证据、生成安装步骤并贯通执行器，未证明Flash会自主选择必要检查、一定提前发现全部依赖或实现稳定降本。下一项宜在新身份下观察真实模型的规划查询、首份方案依赖完整性、首次构建失败、恢复请求及全流程时间/费用；把检查开销与避免恢复的收益同时计入。真实调用尚未开展，旧一次授权已完成，不续用余额。

## 证据

- 原件：`/home/yiwei/.codex/outputs/forge-planning-dependency-engineering-2026-11-16-v1`。
- [查询/预算/构建/清理核验](../../benchmarks/analyses/planning-dependency-engineering-2026-11-16/verification.json)、[1405文件内容清单](../../benchmarks/analyses/planning-dependency-engineering-2026-11-16/inventory.json)，inventory SHA-256 `0ed19e2fb208d5adeafd78bb472012c044392c204b451706f2e8d5fd45c68bb7`。
- 可重复接线入口：`scripts/forge_planning_dependency_check.py --output <独立新目录>`，只运行预写模型，不读取凭据。
- 本轮不替换旧结果，不增加E57或独立项目分母，不自动入论文。
