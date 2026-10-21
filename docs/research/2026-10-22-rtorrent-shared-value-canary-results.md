# rtorrent 共享值真实 canary v3 结果

独立 `cpp-build-rtorrent-common-canary-v3` 固定三策略各一次，0/3 strict、3 个已观察槽、0 个未观察槽。共 31 次真实请求、568231 Token，按冻结单价保守估费 0.85067004 美元，未知用量 0。失败保留，无补槽或自动重试。

| 策略 | 请求 | Token | 估费（美元） | 停止 |
|---|---:|---:|---:|---|
| tool_plan_workflow | 1 | 17619 | 0.02423388 | PlanContractError |
| model_plan_workflow | 13 | 248208 | 0.39892512 | AgentWorkflowBudgetExceeded |
| strong_tool_agent | 17 | 302404 | 0.42751104 | AgentWorkflowBudgetExceeded |

## 分层观察与解释

- `tool_plan_workflow`：build执行=False；原完整测试程序观察0/12、完成0/12；精确交付验证=False；clean replay观察=False。read_source共2次、不同参数2种、重复0次；阶段费用见派生JSON。
- `model_plan_workflow`：build执行=False；原完整测试程序观察0/12、完成0/12；精确交付验证=False；clean replay观察=False。read_source共40次、不同参数13种、重复27次；阶段费用见派生JSON。
- `strong_tool_agent`：build执行=False；原完整测试程序观察0/12、完成0/12；精确交付验证=False；clean replay观察=False。read_source共23次、不同参数8种、重复15次；阶段费用见派生JSON。

未执行的测试/交付/replay保留未观察，不能填成这些功能本身失败。原818作者文件及实际cleanup逐槽核验，未放宽12原程序323叶、40生成SHA、双普通ELF/CLI/精确重放。单一已见development族，不是holdout或处理效果比较，不支持策略排名、规划净收益或主线无效。模型规划未完成是当前模型/材料/接口及共同预算下的观察，不能推断规划方法一般无用。

## 工程含义与下一步

#591固定30个历史材料全部通过的局部资格，不能覆盖v3所有未来状态。新材料仍可触发50k门禁；模型规划还存在重复只读和预算消耗。下一步#595前瞻冻结v2/v3全部实际请求及全部材料超限停止包，资格验证系统固定长验证脚本的共同非执行引用/按需只读取回；执行器继续持有并执行原全文。该项是材料接口修复，不是新算法创新，也不把版本前后差当因果效果。资格和独立审计通过后才考虑独立新真实身份。

## 来源、费用与验证

- release `97775a7ecd47870eff9a36ab1eaafc72a3d20d18`，候选 `04be79b1b0b59aadb1ed070a33b0788cd71ffebf3f9a009bb60df9c0fac54e0f`；272固定组件。
- raw `/home/yiwei/.codex/outputs/forge-rtorrent-common-canary-v3`；inventory `1f6a689afa36ca842fa7c2952622ec0e1e613a49368bbbff7282e1c43d9c0518`，5618文件、0链接、87134604字节。
- 独立stdlib全量清单/Git父链/全部请求可逆还原/原响应逐Token费用生命周期/作者文件与测试层/交付重放审计valid；实际容器资源及不存在审计valid，详情见派生JSON两份审计SHA。
- 43相关回归、产品2486 passed/44 skipped/27 warnings及Ruff/615格式通过；最终结果HEAD三CI后仅合科研依赖分支，发布状态以GitHub及会话发布收据为准。
- 本轮总授权10美元，UTC2026-10-21 15:30:52–19:30:52（准备计入）、请求不限、无自动重试；v2 0.82323780美元 + v3 0.85067004美元 = 1.67390784美元，剩余8.32609216美元，不续期。
- 首次启动器误指旧目录，被防覆盖在新formal/账本/Provider前拒绝，0请求；原日志与勘误保留。修正会话启动器后才正式启动v3，旧inventory复核未变。
- RQ3固定分母、P2、主线与用户HTML保持。
