# 规划工具约束与P4三组比较准备

本轮是为下一项Harness消融准备的有限实现与工程接线，不是模型效果实验。用户已同意工具修正也属于Harness优化，要求比较其效果；尚未绑定本批付费预算/时窗。

## 可回答的问题

A（P0＋旧工具行为）、B（P0＋落实工具可用性）、C（P4＋同B工具约束）。A/B区分执行约束作用，B/C区分P4提示增量。三组初始规划独立，恢复Agent保持同一R2及原工具行为，只干预初始规划。不能据此估计完整交互效应或泛称新算法优于所有Harness。

P4原候选7686c24b的1067字节指导未改，R2原指导270becfd未改。过去P3三条负面轨迹发现Schema外读取，并不能证明此次12项目都将触发同样行为，因此既报告全分母完成和资源开销，也单列初始约束实际激活/拒绝情况。多读可能包含必要诊断；不能把所有额外读取等同浪费。

## 实现

PlanningContext保存每次实际请求的可用工具集合，包含结构化方案提交工具。在开启执行约束的初始规划中，Schema外工具调用在实际handler之前拒绝，明确反馈未执行；保留原工具/步骤预算和事件，拒绝不写入新的读取证据。关闭开关保留旧行为，当前产品默认不变。恢复即使收到开关也强制使用原工具行为，避免干预扩散。

入口：[forge_planning_tool_comparison.py](../../scripts/forge_planning_tool_comparison.py)；[正式协议](../../benchmarks/preregistrations/cpp-build-planning-tool-p4-comparison-flash-v1.md)；[任务与作者参考](../../benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json)。分析区分初始/恢复与尝试/实际读取，费用包含失败和恢复；不把被拒绝读取算实际执行。

## 项目覆盖

12个近期Harness评价任务之外的新项目、各组各一次，共36槽。CMake：open62541、libde265、libsndfile、mbedtls；Make：lz4、clib、streem、libtomcrypt；Autotools：libusb、libffi、wolfssl、cava。六种顺序各用两次，按系统交错。

项目来源继承已有论文项目池，论文来源与历史目录接触逐项登记，非最终holdout。smenu系统归类和zlib原输入重命名冲突均在任何方法运行前发现并替换，采集原件保留。独立参考来自固定作者源码，保留默认主要组件；libsndfile的十个工具和clib的九个工具不随意删减。库不虚构执行测试，CLI采用作者版本/用法，作者明确正常退出1与超时/异常区分。clib主版本检查存在网络接触，三组保持相同定义。

源码材料：`/home/yiwei/.codex/outputs/forge-planning-tool-p4-sources-v1/source-index-final.json`。12项目已完成作者定义和源码归档核对，不声称它们均已预先真实构建通过。

## 已观察的零费用验证

真实LangChain图5项验证覆盖开关、单/批量隐藏调用、拒绝反馈/预算/不产生新证据、恢复保持旧策略。另5项比较入口验证覆盖36槽顺序、独立规划与恢复一致、零Provider检查与未授权门禁、分阶段读取计量；连同旧P3相邻检查共17项通过；57项相邻规划/构建/组件/分层检查通过，Ruff/格式通过。旧pytest临时目录的权限清理警告属于已有残留，不影响本轮通过与新容器清理。

旧linenoise两条脚本模型真实构建均通过主构建、作者轻量运行、交付、实际干净重建、源码保护及清理。A实际执行5次读取；约束路径5次尝试中执行4次、拒绝1次。受控脚本都使用6条预定回复，不估计真实模型请求/费用改善。工程材料：`/home/yiwei/.codex/outputs/forge-planning-tool-policy-engineering-v1/{scope,summary,verification,completed}.json`，含运行脚本与源码快照；4容器8个名称/ID实查不存在。

## 正式运行边界与下一步

新增模型费0，正式0/36，无活动Provider，论文与旧E56不改。本轮建议预算硬上限5美元、确认起8小时；固定Flash、无自动重试/不补槽，未知用量/模型标识异常/清理失败停止整批。单槽最多0.40美元/1800秒，干净重建600秒。用户确认本批预算及窗口后执行正式比较，结果另交审核再决定入文。

冻结manifest：`c0d2e3d55fa54737ff05759242da915bee6b246b63110334c425f0bc6267b611`；真实零Provider检查通过。代码发布见Issue #746关联PR，准备报告不登记为新增论文实验结果。
