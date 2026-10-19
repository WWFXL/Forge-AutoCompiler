# 双臂真实开发canary v1：读取接口缺陷使比较失效

Issue #486，identity `cpp-build-plan-agent-canary-v1`，运行release `6075f1ce531f81d6f45632ef3f82ecc1bc137b42`。8/8预定臂均已分类终结、源码未变、cleanup成功，证据和用量独立审计valid=true。决定为 **`repair_read_tool_contract_before_comparative_claims`**：本轮观察不能用于主张Workflow优于工具Agent。

| 项目 | 完整方案+Workflow | 工具Agent | 请求数 plan/tool |
| --- | --- | --- | --- |
| miniz | strict completed | 绝对源码路径被拒，0执行命令 | 6 / 3 |
| md4c | strict completed | 绝对源码路径被拒，0执行命令 | 2 / 3 |
| pigz | strict completed | 列举不存在的src目录抛FileNotFoundError，0执行命令 | 5 / 3 |
| libite | 列举不存在的aux目录抛FileNotFoundError，0执行命令 | 两条diagnostic后绝对源码路径被拒，未进入构建 | 3 / 5 |

三个完整方案成功臂均通过固定完整测试、精确交付、clean replay、重放测试和清理。四个工具臂没有实际编译尝试，不能称为四个构建能力失败。libite方案臂也受相同读取缺陷影响。路径只接受规范相对名，但工具Agent接收的Shell提示使用容器绝对路径；无效或不存在的读取调用又被框架提升为整臂终止。零Provider八臂门禁使用人工参考响应、没有主动触发读错路径，因而未覆盖此缺陷。

另一个开发观察是多次重复目录/源码读取。当前模型材料仅保留最近三个工具反馈，旧读到的证据可能丢失；这是可核验的Harness解释假设，尚未通过反事实或消融证明。不能据此给当前成本做事后减法，也不能把修复前后差值称方法效果。

## 用量与证据

本轮30 requests，201,694 input +26,446 output =228,140 recorded tokens，已知保守估算$0.37096224；0未知usage，不是实际账单。plan合计16请求/131,515 tokens/$0.2346894；tool合计14请求/96,625 tokens/$0.13627284。工具臂提前终止，费用与成功率均不具比较解释，禁止计算或宣传成本节省比例。

阶段整额$12已在封存后结算释放。新增总费用：跨系统v1/v2 $0.3727878 +本轮$0.37096224 = **$0.74375004** 已知估算；旧live测试未知费用预留$1，合计$1.74375004。没有未结束付费阶段，共享上限仍$20，截止北京时间2026-10-20 07:00。

原始：`/home/yiwei/.codex/outputs/forge-plan-agent-canary-real-v1/`。
类型化inventory：1388普通文件、14链接、36,164,553 bytes；canonical SHA-256
`16c7f19f3c9b0b7f40284e3ff71b217b7bffcbe220810d85e419c84a025838f0`。
独立审计：`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/plan-agent-canary-real-v1-audit.json`，核验完整文件/链接集合、原始源码、响应用量守恒、固定oracle、strict Session/replay及cleanup，valid=true。
manifest SHA-256 `c2f51f45e7d42cdb5799155a092dd31b3f26d1f1bf892480c3f27afb56f8d583`；协议和代码快照随原始目录冻结。

## 下一阶段

#489独立工程修复：安全容器路径别名、可恢复读取错误反馈、带来源的有界证据工作集；不扩大源码/日志读取根，不隐藏重试，不改测试或严格验收，先真实图与零ProviderDocker验证，再冻结新身份。#488核验ReAct/ReWOO/LLMCompiler已有方法并设计静态/规则/状态适应消融。

本身份永久封口，不续跑、不补填、不替换。后续相同开发任务的修复接线结果也不能当独立holdout或正式处理效应。尚未证明真实故障恢复、状态选择器增量、总体非劣、成本收益或论文创新点全部成立。
