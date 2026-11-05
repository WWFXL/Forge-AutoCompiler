# 固定Flash下基础Forge与两层经验比较结果（2026-11-05）

## 问题与结果

在共同规划交付/容量修复之后，本轮分别检验跨项目条件建议与同项目成功方案复用，各16次、各自两方法8次。32/32终态、0未启动槽，31次完整成功，一次基础规划接口失败；不合并两项效果分母。结果支持精确重复任务复用已验证方案，未支持当前跨项目建议降低正常规划成本。

| 独立比较 | 方法（各8次） | 主构建/完整 | 模型请求 | 在线估费USD | 累计秒 | 初始规划秒 | 源码补读 |
|---|---|---|---|---|---|---|---|
| 跨项目建议 | 基础Forge | 8/8，8/8 | 17 | 0.0512544 | 410.47 | 37.56 | 9 |
| 跨项目建议 | 跨项目条件经验 | 8/8，8/8 | 22 | 0.0728724 | 418.60 | 46.11 | 14 |
| 同项目复用 | 基础Forge | 7/8，7/8 | 21 | 0.0645282 | 395.35 | 42.25 | 13 |
| 同项目复用 | 同项目精确方案复用 | 8/8，8/8 | 0 | 0.0 | 372.65 | 0.00 | 0 |

跨项目建议：同等完整8/8，请求增29.4%、费用增42.2%、累计时间增2.0%；源码补读9→14，重复读取均0。两组全部成本来自初始规划，恢复请求0。经验每槽一次检索，共8次/22682字节；不是每轮重复检索或旧50请求循环。jsoncpp/highwayhash两组分别均4/2请求，经验上下文增加费用；libsrtp请求6→8、libite5→8，额外读取进一步增加费用。四项目汇总不是总体显著性推断。

同项目复用：8次精确命中、0次模型请求，原源码/完整作者测试/交付/clean replay/cleanup全通过，仍实际重新编译，没有复用二进制。基础Forge7/8完整、21请求；一次规划失败的费用也计入0.0645282美元。两组累计395.35/372.65秒相差5.7%，但基础含一次7.06秒早停，不把全分母累计时间差当同等完成量加速。共同完整的7对累计388.29/349.42秒，复用低10.0%，仅是按完成筛选的辅助描述；相应基础费用0.0577356美元。整体时间还受所选方案及编译/测试/replay影响，不把全部差值归因省去规划。

## 方法和公平范围

四项目为jsoncpp（CMake）、libsrtp/libite（Autotools）、highwayhash（Make），全部已经开发暴露。每项四项目×两重复×两方法16次，相邻配对、第二重复反转顺序。两组同deepseek-flash thinking low、同修复后的共同Harness、相同公开简洁任务/源码归档/不可变镜像/并行资源、Workflow、方案式恢复及独立检查。此处Forge是简洁构建研究执行入口，不将旧产品Lead/Compiler实现混作处理。

基础Forge：模型只读必要源码，返回dependency/configure/build动作，Workflow执行；失败交给同一模型返回修订方案。跨项目经验Forge：保留同一规划流程，只在每个新Agent任务开始检索旧24条/8来源族/12轨迹库，最多两条/4096字节；库和来源族隔离，不在线更新。本批没有同项目方案，也没有新Astra提炼。

同项目经验Forge：按公开任务精确匹配历史方案（仅排除运行标签plan_id），匹配后直接交Workflow；失败仍可交同一Flash修订，本批未触发。两组均不注入跨项目建议。来源前瞻固定为E45第一重复Flash槽1/4/5/8，不按最低费用或本批结果挑选；四方案各自SHA及来源inventory写在manifest。本批成功不供后续重复使用。

任务只要求作者Linux普通主程序/库，不给千奇百怪的Debug/静态库等目标。规划输入为公开任务、初始README/根构建文件及只读工具反馈；私人知识库与独立参考命令不进入实验Agent。作者测试选择实际顶层构建系统对应入口、拒绝零测试；不声称CMake与Autotools测试集逐项相同。

## 解释案例

1. **弱相关建议造成额外上下文。** jsoncpp检索了来源E30-slot-19/24的外部测试依赖/FetchContent建议；本次原项目无该已观察失败，两组请求相同但经验费用增加。libsrtp/libite检索E30-slot-1的文档makeinfo经验，正常构建没有相应失败；libsrtp两重复每次基础3/经验4请求。highwayhash经验的匹配词只有`state`，不能据此确认建议适用。这些是检索精度与条件建模的线索，不是已证实的单条经验因果效应。
2. **有效成功方案避开重复规划。** libsrtp直接复用`./configure`→`make -j2`，libite复用`./autogen.sh`→`./configure`→`make -j2`。两重复均零模型完整通过，重放仍在空环境执行完整配方。jsoncpp历史方案关闭重复的post-build unit-test钩子，但原测试仍由独立CTest完整执行，并非关闭作者测试。
3. **基础组一次接口交付失败。** 同项目批槽8/highwayhash：第一响应已给出有依据的`make -j2`，但附带`diagnostic_paths=["/workspace/repo"]`不满足相对路径schema；一次计费纠正改成`["."]`仍被拒绝。两次响应/0.0067926美元保留，未到Workflow编译；主构建/测试/交付/replay及源码终态未观察，cleanup成功。这不是空方案或编译器报错，不能用复用组通过宣称更强编译修复能力。未来可减少模型负责的非核心元数据，本轮未放宽接口或重跑失败。

## 来源费用与科研边界

本轮只新增60响应、输入566690/输出15540、共582230记录Token，保守估费0.1886550美元；逐响应复算与槽账本、初始/恢复分项一致，未知用量0。Flash输入0.30/输出1.20美元每百万Token按全部输入未命中缓存保守估费，不冒称账单。

旧库一次提炼费0.095129美元另列。四份成功方案历史来源构建费0.0314205美元，也另列，不在本轮再次支付。仅计这四次来源构建，复用累计模型费用为0.0314205美元；若将整个旧库也一次性全额归入该部署，累计为0.1265495美元，高于本轮基础8次0.0645282美元。后一情景只作成本分配展示，不把历史投入说成免费，也不据8次重复任务推长期回本时间或持续自进化。

本轮可以用于第5章两层经验设计、第6章经验组件比较及失败分析。它不证明未见项目泛化、恢复/状态选择的独立收益、经验在线学习能力或当前Forge优于强工具/CXX；两个独立分母不合并，两重复不当8个独立项目。E40/E41、E42/E43旧失败与E44/E45全部保留，不能以跨批差值估计修复因果。论文完整稿仍v0.6，本轮仅补充可直接取用的报告/表格/案例和证据入口，不冒称Word/PDF全文已经更新。

建议下一步先采用清晰的两层边界：同项目精确复用已有实证支持；跨项目建议需提高适用条件精度，优先评估真实失败/明确缺口下的触发，而不直接扩大正常规划注入。该建议尚非新实现或新效果，未来验证需独立设计；不因此推翻整体状态感知Workflow主线。

## 执行与证据

授权为用户“好的开启比较基础 Forge 与经验 Forge”及已有仓库/实验授权；助手自行限定新增2美元、UTC2026-11-05 00:30:44–02:30:44，准备计入，两个身份共享，未借用旧余额。正式进程已退出，无活动Provider，无自动重试/补槽、没有修改冻结组件/验收/失败；32槽cleanup成功，31槽源码终态通过、1槽未观察。63个compile/replay容器的126项名称/ID实查均不存在。

运行release：`c8e394c779f89eeb12dba9cce01ccdf83f1e192c`，共同后端方法继承E45已修复实现。新增5项编排检查与Ruff通过，只证明处理隔离、共享扣费及异常停止；运行提交三项CI均SUCCESS，不计模型效果。

| 实验身份 | manifest SHA-256 | 原件与inventory |
|---|---|---|
| `cpp-build-repaired-cross-project-experience-flash-v1` | `c2def2b7f63fc86bc6b80c280879d8535321099b5d5ce1ef58eedbb14068e6c1` | `/home/yiwei/.codex/outputs/forge-base-experience-comparison-v1/advice`；`978f7e11f58c956d0f6191b56177829f5fad285e9fce277a383987a46f4aecef` |
| `cpp-build-simple-project-reuse-flash-v1` | `3805b2e9e9bdc85ca0b26ec96eeba08ee6dce622ea7f893b8cab6361711b9022` | `/home/yiwei/.codex/outputs/forge-base-experience-comparison-v1/reuse`；`6940b019dc18abff6acab2a25116250ed5e0441fd1086010b3aee6cf2039be91` |

[原协议：跨项目](../../benchmarks/preregistrations/cpp-build-repaired-cross-project-experience-flash-v1.md)、[同项目](../../benchmarks/preregistrations/cpp-build-simple-project-reuse-flash-v1.md)及同名manifest；[分析汇总](../../benchmarks/analyses/base-experience-2026-11-05/summary.json)、[跨项目逐槽CSV](../../benchmarks/analyses/base-experience-2026-11-05/advice/slots.csv)、[同项目逐槽CSV](../../benchmarks/analyses/base-experience-2026-11-05/reuse/slots.csv)和各目录的pairs/experience-contexts/response-verification保存全部费用、提示上下文选择与失败指针。可运行`backend/.venv/bin/python benchmarks/analyses/base-experience-2026-11-05/analyze.py /tmp/forge-analysis-new`只读复算，目标目录必须尚不存在，不能改raw。会话授权/运行日志/资源/最终发布收据在`/home/yiwei/.codex/outputs/forge-base-experience-launch-v1/`；两个raw分别类型化封存，后续分析不写回原件。

发布仅科研集成分支`yiwei/534-rq3-natural-failures`，Issue687/PR688最终状态以GitHub及会话收据为准，不进main。原生Git两次TLS失败后明确使用Git Data API备用路径发布相同SHA/tree，不改凭据/代理。用户原memory修改、HTML及uv.lock保留；个人知识库仅经MCP同步，不注入Agent。
