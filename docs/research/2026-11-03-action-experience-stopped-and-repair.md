# 短动作经验：提炼完成、批调度中止及初始覆盖分析

状态：12/12次提炼完成，13条经验；36个构建比较槽全部未观察。新增估费0.164217美元、未知用量0。批入口错误已修复，独立v2已准备但未授权启动；材料覆盖分析发现当前C库在六项目初始规划均为空，应先决定如何处理这一限制，而非直接重复整批。

## 本轮执行与实际结果

用户批准原固定协议`cpp-build-task-action-experience-flash-v1`及`cpp-build-task-action-distillation-richlab-v1`，共享新增10美元硬上限，UTC2026-11-03 09:52:44至17:52:44（北京时间11月4日01:52:44），无自动重试、失败不补槽。计划原六项目各两重复×无经验/旧来源经验/短动作经验，共36槽；另固定12份历史来源各一次提炼。

唯一启动进程1720695于UTC09:55:32开始，10:01:37异常退出，launcher记录IndexError；没有重新启动。完成12次提炼后，三组比较借用了旧四组批循环。循环在构造首槽经验库时读取METHODS[3]，但新METHODS只有三个元素，因此在进入run_slot、创建编译Agent、构建容器及首个构建模型请求前中止。slot-1仅保存experience-bank-used.json，没有Agent事件、请求或响应。

原result.rows为空、unobserved_schedule完整保留36项；stop_reason为null，这是异常路径没有为该字段赋值，不能解释为无错误完成。最终事件以launcher-final.json及异常日志为准。不能写成0/36构建成功率、36次构建失败或短动作经验无效，也不能用零构建费用/短时退出当效率优势。

| 项目 | 实际观察 |
|---|---|
| 固定来源提炼 | 12次请求、13条通过结构/来源绑定的经验、0内容拒绝 |
| 输入/输出Token | 141936 / 22281，共164217 |
| 提炼估费/累计调用时间 | 0.164217美元 / 364.933秒 |
| 条目结果标签 | 9局部effective、4未执行hypothesis；不等于9次完整任务成功 |
| 条目阶段 | dependency 4、configure 3、build 3、verification 3 |
| 构建比较 | 计划36、实际终态0、未观察36；三个方法各12未观察 |
| 本轮新增费用 | 提炼0.164217、构建0；未知用量0 |

12次提炼均请求RichLab gpt-6-astra路由、响应model为gpt-5.6，沿用用户已接受的披露；不能证明后端确为Astra或更强。输入/输出均按用户给定1美元/百万Token估费，不代替服务商账单。

## 初始材料覆盖：一项独立于入口错误的研究限制

修复期间使用已形成的固定13条库、原六项目的初始任务和源码归档静态事实，只读执行实际ActionBank选择器。没有加入未来失败，没有模型调用，没有修改经验库或正式raw。jsoncpp、PEGTL、inja、highwayhash、libsigcplusplus、libsrtp六项初始结果均为空，0/6有材料。

具体原因是部分条目把来源项目特有的选项、符号、文件或测试程序设成跨项目必需字面条件：例如snappy的四个依赖符号、yaml-cpp专用选项、tinyxml2源码文件和ELFIO测试开关。它们可以绑定真实来源，却难以在不同项目族上成立。另一些条目要求当前错误或生成后的CMakeCache.txt，初始阶段不能提前提供。libsigcplusplus没有其他Autotools的无错误初始条目可用。此分析只说明当前固定库/选择组合的初始覆盖，不推断恢复阶段也必然为空，亦不证明放宽后能安全迁移或降低费用。

因此，原三组比较即使正常运行，C的初始规划也不会获得实际经验材料；它仍可观察失败后检索，但不足以检验本轮主要问题“短动作经验能否减少初始规划探索”。这是材料适用性与选择的研究限制，不是观察到的模型负效应。不能只为了得到非空结果删除必要条件；应区分来源特定事实、可迁移的构建能力条件和需要当前Agent核对的前提，并以独立版本评价。

## 已完成的必要修复与准备

执行修复仅把旧批循环的条件改为明确策略名conditioned_experience，不再以第四个位置识别策略；其四组既有语义不变。原冻结源码快照、manifest、result、seal及旧实验均不改写。

此前单槽端到端检查没有经过真实整批选库分支，遗漏了该错误。本次新增零Provider批循环回归，实际遍历三组36/四组48个脚本槽，覆盖选库、分派、汇总及共享已付提炼费；未授权v2必须在复制种子或进入付费入口前停止。相关8项检查通过、Ruff/格式通过。这些是工程验证，不是84次模型效果，也没有重跑参考构建或产品全测。

独立`cpp-build-task-action-experience-flash-v2`提供复用13条原种子的可审阅候选，不重新提炼。其方法、六项目、两重复、36槽顺序、原验收和预算/截止均拟保持；只修调度，不解决上述0/6初始覆盖。新manifest已绑定种子/提炼收据/旧授权哈希，准备和组件检查通过；新authorization及正式raw不存在。它不是已执行结果，也不建议忽略覆盖问题直接付费。若要改变经验条件/选择，则需另冻结修订协议，不悄改本候选。

## 证据与论文用途

- [派生分析](../../benchmarks/analyses/cpp-build-task-action-experience-flash-v1/analysis.json)保存全分母、费用及原证据哈希；[初始覆盖](../../benchmarks/analyses/cpp-build-task-action-experience-flash-v1/initial-coverage.json)与同目录selection日志保存逐条排除依据。
- 原raw：`/home/yiwei/.codex/outputs/forge-task-action-experience-flash-v1`；seal canonical SHA-256 `ac54095a90219e3c6dd0ed6945e2bb6ab70f93b24ed169b2bd0cd8c1fb4c0d36`，360普通文件/0链接/4153624字节。
- 授权/12次提炼/seed-bank/失败日志/最终进程收据：`/home/yiwei/.codex/outputs/forge-task-action-experience-session-v1`。运行release `ec536e2197bd26e78fdfc51463f08d58020f8a33`、候选`fe24c108675e64c31d62e901734fad9b49a509fc71c7d40f8707decb2c6226be`、355组件，失败现场源码随raw封存。
- [v2协议](../../benchmarks/preregistrations/cpp-build-task-action-experience-flash-v2.md)、同名manifest及[scripts入口](../../scripts/forge_build_action_experience_v2.py)。Issue #664继续跟踪，修复PR不关闭尚未完成的比较任务。
- 论文索引E38仅登记材料、适用性局限和工程失败；不列完整效果实验。E37/E35/E36及v0.4既有结果继续对应原版本。第5章补充任务快照/短动作表示，第6章交代未观察范围，不添加效果表或覆盖旧导出稿。

## 下一项决定

建议先处理当前库的跨项目初始适用性，再开展能回答研究问题的独立36次比较。区分“保守排除有依据”与“用来源专用符号把全部迁移机会排掉”，并保持原源码/测试及完整验收。原固定协议无自动重试，用户批准的是v1；新身份或修改选择条件需明确范围。原10美元预算尚余9.835783美元、截止不重置；本轮已付提炼可复用，不应因入口错误再次支付。
