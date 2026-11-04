# 简洁规划、经验注入与测试入口改进

2026-11-04，Issue [#681](https://github.com/WWFXL/Forge-AutoCompiler/issues/681)。本阶段完成工程修复与实验准备，**0真实Provider、0新增模型费**。四条脚本Agent驱动的真实Docker构建均完成主构建、作者测试、精确交付、干净重放、原源码保持和清理；它们证明实现可运行，不是Flash效果实验。

## 为什么改

[E42结果](2026-11-04-simple-system-comparison-results.md)中，7次Forge未完成都在初始规划阶段；经验组三个50请求读取循环占其模型费约80.2%。本轮逐槽核对还纠正一项描述：槽16/28/30的工具参数为`{}`；槽44/libite有完整动作，但步骤列表放进了reason、缺少steps。四次均是规划结构交付错误，不能统称模型完全不会规划。旧原件、费用、分母和未观察层不改。

共同缺陷由两Forge一起修复；经验是否有益由新配对比较回答，不能将旧新版结果之差直接解释为经验或状态感知增量。

## 已实现的行为

|组件|新行为|实现|
|---|---|---|
|规划交付|精简SimpleBuildActions；去掉旧files_exist等观察字段；完整示例；原生ToolStrategy提供一次显式结构纠正，第二次仍错停止，Provider错误不续问|`simple_build_task.py`|
|对话保留|保留真实AI/Tool历史与格式反馈；49KB不足时按完整调用/结果组淘汰，保留有限助手正文和读取索引；不用额外摘要模型|`simple_planning_context.py`、`simple_build_agents.py`|
|规划收敛|入口与必要阶段指令有依据即可交付；连续两轮读取无新内容提示收敛，三轮后只暴露输出工具；新区间/内容变化会重置；明确阻塞不得造方案|同上与规划提示词|
|经验|一任务一次检索；仅匹配当前证据与条目适用条件/状态，按阶段过滤，最多两条/4096字节；保留禁用条件和来源依据，无匹配弃权|`simple_build_experience.py`|
|独立测试|实际顶层CMake配置走实际构建目录的作者CTest，零测试报错；其余保留固定作者入口；记录选择，成功测试同命令进入replay|`simple_author_tests.py`、`simple_build_runtime.py`、CXX外部检查|

经验仍来自同一旧冻结库，不重新请Astra提炼、不在线更新、不把个人知识库注入实验。新输出仍装配为既有Workflow阶段动作；独立主产物参考不送模型，也不由模型修改。

容量压缩会丢弃较早的完整交互，助手正文也只是有界保留，不能宣称任意长任务不遗忘。收敛提示依据重复工具反馈而非语义理解全部充分性，仍可能提前终止有用探索；正式结果必须保留这些失败。经验词项匹配不是语义检索，也不保证选中的建议适用。

## 实际验证结果

44项相关行为检查通过，覆盖三次空参数/字段错位的代表性形式、仅一次纠正及原响应/费用保存、服务错误不纠正、早期证据与助手正文保留、完整交互压缩、读取越界拒绝后继续、重复读取收敛、经验阶段/来源/容量弃权、真实本机CTest通过与零测试拒绝，以及16槽顺序/分派和授权绑定。Ruff/check与format通过。未重复本地全量产品测试或旧资格链；PR规定CI仍须完成。

四条真实Docker路径的模型回复都是显式脚本：

|项目/方法|验证的异常或路线|脚本响应次数|主构建/作者测试/交付/replay/源码/cleanup|总秒|
|---|---|---:|---|---:|
|jsoncpp/基础|先返回空参数，再纠正；非标准CMake目录|2|全部通过|47.91|
|libsrtp/经验|公开标识Autotools，实际选择作者CMake；自动选CTest|1|全部通过|54.19|
|highwayhash/基础|四次相同README读取后，下一请求只提供输出工具，再执行Make|5|全部通过|23.50|
|libite/经验|步骤错放reason后纠正，autogen/configure/make|2|全部通过|61.94|

共10次零Token模拟响应，0真实Provider；两经验任务各检索一次、约2323/2321字节。四个compile及四个replay容器的名称/ID共16项实际检查均不存在。源码/测试未修改。不能拿脚本给定的正确方案证明Flash规划成功率提高，也不能拿本表时间估计模型加速。

原件在 `/home/yiwei/.codex/outputs/forge-planning-improvement-engineering-2026-11-04-v1`，含driver/scope、实际运行前代码快照、四任务请求/响应/拒绝/工具/命令日志/方案、分层结果/交付/replay及resource-check。封存inventory为`23dae3a2cc2ba639588b65d06aceac2743120692ae6c5c3d473f5c903d0f94eb`，8493普通文件/44链接/74217668字节。运行后补充了读取别名/拒绝反馈和parallel_tool_calls设置的稳健性修复，已由相关离线图检查覆盖；`runtime-snapshot`保存运行时版本，`source-snapshot`保存这些最终小修复，不能将最终发布commit冒充前述早期运行版本。

## 准备好的真实比较

身份为`cpp-build-planning-context-experience-flash-v1`，见[协议](../../benchmarks/preregistrations/cpp-build-planning-context-experience-flash-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-planning-context-experience-flash-v1.json)和入口`scripts/forge_planning_comparison.py`。四项目×两重复×改进基础Forge/改进经验Forge，共16槽、各8槽；共同Flash low、同源码/目标/镜像/资源/Workflow与恢复，固定旧经验库，无新提炼、无同项目配方、无在线更新。

主要记录初始方案交付、主构建与完整完成、全部请求/费用/耗时、格式纠正、重复读取和经验检索/弃权。四项目已有开发暴露，属于开发机制比较；不声称泛化或每项修复的独立因果。CTest与Autotools原生测试集可能不同，记录适用入口与范围，不和旧E42完整率相减。旧E01/E30/E33/E35–E42及论文v0.6保留，不新增效果编号或将本阶段工程检查计入正式16分母。

准备/检查入口不读模型凭据、不调用Provider。正式运行需要新授权绑定具体身份、manifest SHA、预算及确认时窗；建议新增费用硬上限10美元、确认起4小时，SDK无自动重试、一次显式格式纠正计费，未知用量/身份异常/清理失败停止整批，不补槽。本阶段当前未启动16次，旧批预算余额不续用。代码通过相关检查和CI后仅合科研集成分支，GitHub是发布状态权威，知识库同步长期进度。

准备检查通过，manifest SHA为`7a59cc565c2bcfc0ca751b634424e0d926e5d6580a72a66f7c32574f4781bd2b`；正式16次仍未启动。
