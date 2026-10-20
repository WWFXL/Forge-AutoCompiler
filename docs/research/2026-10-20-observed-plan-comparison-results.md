# 观察接口十二槽真实比较：HTTP402停止结果（#550）

本轮按新授权实际执行，但首次模型请求再次返回HTTP402，用量未知，按冻结协议停止整批并封存。没有形成三策略效果比较；这次服务异常不能解释为规划、恢复或构建方法失败。

## 身份与授权

- 身份：`cpp-build-observed-plan-comparison-v1`，manifest为`benchmarks/manifests/cpp-build-observed-plan-comparison-v1.json`，SHA-256为`8a9310f8c89d657b29d9a1b7f56b967c17ba615a2717d2239fda139293bade2b`。
- 用户授权新增模型费最多20美元、4小时，UTC2026-10-20 14:19:33至18:19:33（北京时间2026-10-21 02:19:33），准备计入；授权登记见同目录`2026-10-20-observed-plan-comparison-authorization.md`。
- 运行release为`86a7f59cacd12d3bfb0fcc059414e1852ab47c78`，冻结120组件不变。libpng/check/libtommath/libsodium各一次×工具规划Workflow＋失败Agent、模型规划Workflow＋失败Agent、强工具Agent，共12槽；原DeepSeek Pro thinking low、资源、完整测试/原源码/精确交付/clean replay裁判不变。
- 本轮是定向已见开发任务，非holdout。两Workflow共用观察、测试装配、暂存和恢复；强工具为整策略参照，不能称三者只差规划。全初始/失败/纠错/恢复费用计入。

## 观察与停止

实际CLI零Provider preflight通过。唯一启动器于UTC14:22:10.679312启动，付费stage于14:22:18.541142开始、14:22:23.560447关闭。首槽`00-libpng-r1-tool_plan_workflow`中，保守工具模板拒绝后升级为`initial_abstention` Agent，首请求出现`APIStatusError`，原始事件`status_code=402`。该槽总臂时间4.557144秒。

按未知用量停止规则，进程退出码1，生命周期闭合、证据封存；没有自动重试、替换或补槽。`result.json`的`stop_reason=cleanup_or_unknown_usage`经独立原始事件与Docker审计细分为Provider HTTP402未知用量，实际cleanup已通过，不能从合并停止标签推断清理失败。

| 策略 | 计划槽 | 请求被观察槽 | Provider前置阻塞 | 未观察槽 |
| --- | ---: | ---: | ---: | ---: |
| 工具规划Workflow＋失败Agent | 4 | 1 | 1 | 3 |
| 模型规划Workflow＋失败Agent | 4 | 0 | 0 | 4 |
| 强工具Agent | 4 | 0 | 0 | 4 |

唯一请求没有完成响应，没有生成方案、执行Shell、Workflow转换、恢复交接或replay。首槽记录`strict_completed=false`表示未完成严格终点，不代表观察到了构建方法失败。0可比较项目对，不计算策略排名或效果差值。

| 验证层 | 本轮观察 |
| --- | --- |
| 构建、作者固定完整测试、精确交付、clean replay | 全部未观察 |
| 原源码 | 未改，核验通过 |
| 实际清理 | 原容器ID与名称均不存在，独立核验通过 |

## 用量与费用

1请求、0完成响应、1未知用量请求；记录Token为0，仅表示没有返回用量，不能说实际用量为0。已知完成响应估费0.00美元、未知请求预算预留0.40美元、预算占用0.40美元；实际模型总费用为未知（null）。预留不是账单，本次不称免费，也不是20美元预算耗尽。无额外服务探针、充值或Provider切换。

## 证据与核验

- 永久只读raw：`/home/yiwei/.codex/outputs/forge-observed-plan-comparison-v1/`。inventory SHA-256：`0a859d724b8e37e2c683e5531397cf0135fbd499a416ec12dbf7ce43e424e778`；698普通文件、0链接、11,751,288 bytes。
- 本轮会话：`/home/yiwei/.codex/outputs/forge-observed-plan-real-session-2026-10-20/`。含授权、preflight、唯一启动记录、进程退出、started/completed预算事件、`descriptive-results.json`、独立审计和发布/知识库收据。`launch_real.py`仅为已执行启动记录，禁止再次运行。
- `independent-real-audit.json`与`final-budget-audit.json`均`valid=true`：inventory、120组件snapshot、原始HTTP状态、请求生命周期、源码、实际容器清理、费用预留、时窗和停止均闭合。
- 独立stdlib实现`audit_real.py` SHA-256：`d879738b9bca836be556a733f1364e9d693f62baff94b0a09df5d24d17e9d181`；`audit_budget.py` SHA-256：`ed84d1b63ef4b5cc7b0f382034137048424025cc682ed00a11ca7e8d98ae4da6`。旧证据、旧审计及冻结组件未改。
- 本轮本地`make -C backend lint`通过（556文件格式检查）；`make -C backend test-product`为2131 passed、44 skipped、27 warnings，exit 0。历史pytest临时目录权限清理警告保留，未删除其他任务目录。检查日志位于本轮会话；这不增加方法效果证据。
- 最终HEAD三CI/发布状态以会话日志、`final-publication-audit.json`及GitHub为准。仅发布到依赖分支`yiwei/534-rq3-natural-failures`，不进入main；用户未跟踪HTML不改、不提交。

## 结论与下一步

此次只证实首次真实请求仍遇HTTP402且用量未知，未知停止和清理路径实际生效。不能判断规划收益、接口修复的真实效果、恢复能力、成本优劣或自然失败成功率；不将未观察填为通过/失败，不与旧批次差值作因果。

先处理Provider外部服务阻塞；账户/服务端具体原因尚未核验，不能声称余额不足或服务已恢复。本身份永久停止，不以剩余额度另开付费身份、探针或补槽。服务恢复后另冻结身份并核验新授权，再继续公平比较。硕士主线保持，接受小幅或条件性收益；不加P2、不改RQ3固定分母、不降验收标准。
