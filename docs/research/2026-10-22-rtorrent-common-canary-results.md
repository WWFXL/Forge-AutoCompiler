# rtorrent 真实三策略 canary：多轮材料边界与费用

## 问题与身份

本轮为真实数据采集及结果分析，跟踪 #589。`cpp-build-rtorrent-common-canary-v2` 在同一个已见 rtorrent/libtorrent development 项目族上，按工具方案 Workflow、模型方案 Workflow、强工具 Agent 的固定顺序各运行一次。它不是 holdout 或总体效果比较。两 Workflow 共用装配、恢复和验证，强工具 Agent 为整策略参照；全部初始读取、规划、输出、失败和恢复均计费。

用户最终授权新增模型费用 10 美元、UTC 2026-10-21 15:30:52–19:30:52（准备计入）、请求次数不限、无自动重试。取消旧候选的十二请求独立上限，仍共同限制 72 steps；技术请求上界 73 不会先于 step 生效。实际模型 deepseek-v4-pro、thinking enabled/low、SDK max_retries=0；原 50,000 字节消息、8,000 字节 schema、Token/工具/命令及原源码、完整测试、精确交付、clean replay 与 cleanup 标准保持。旧候选和旧失败不改、不续跑、不补槽。

候选：`benchmarks/manifests/cpp-build-rtorrent-common-canary-v2.json`，SHA `480057ef52ec06743f2515e7acd855ec6d52954c1287ab1c8d1d02ba1a73e636`；运行 release `3aa16e6c2bb8600c93122d2b24022cd60e2f2be6`。详细资源、任务与停止规则以同名 manifest/preregistration 为准。

## 观察与全成本

三槽均已观察、严格完成 0/3、未观察槽 0；全批 stop_reason=null，三个方法失败原样保留并正常走完固定顺序。共 28 次真实请求，输入 491374 / 输出 44097 / 总 535471 Token，保守估费 **0.82323780 美元**，未知用量 0。本轮预算剩余 9.17676220 美元，原截止不延长。

| 策略 | 请求 | 总 Token | 估费/美元 | 总墙钟/秒 | Shell 命令 | 终止位置 |
|---|---:|---:|---:|---:|---:|---|
| tool_plan_workflow | 1 | 18938 | 0.02638416 | 84.287484 | 3 | 第二次请求前材料超过 50k |
| model_plan_workflow | 16 | 320512 | 0.51499008 | 823.385036 | 1 | 规划未提交，AgentWorkflowBudgetExceeded |
| strong_tool_agent | 11 | 196021 | 0.28186356 | 366.239958 | 5 | 后续请求前材料超过 50k |

工具方案初始规划模型费用为 0，实际通用模板 autoreconf 成功，configure 因缺 libtorrent 真实失败，然后一次恢复模型响应调用三次 list_source；后续材料在第二响应前被拒绝。模型方案的 16 次请求全部属于初始规划；44 次 read_source 中只有 13 种路径/起始行参数，31 次重复，加 4 次 list_source 达到 48 次只读工具。终态 snapshot 为 64 steps / 320512 Token / 约819秒，支持其到达工具预算的解释；row 没有保存异常理由字符串，不能伪称错误原文写了这一理由。强工具 Agent 的全部 11 次请求属于 tool_agent_run，不拆称初始规划；12 次 read_source / 7 种参数 / 5 次重复，26 次工具调用。

三个槽都**没有执行 build**。完整作者测试、精确交付、clean replay 均未观察，不填功能测试失败。三个槽 818 原作者文件保护、文件边界及实际容器清理通过。没有活动 Provider、构建或 replay 容器。

## 审计与证据

原始冻结证据：`/home/yiwei/.codex/outputs/forge-rtorrent-common-canary-v2`；typed inventory SHA `271bcecbd2d17abae1c5358beffcf43b54d223a62d228e20a5ca330599b0d2be`，5437 文件 / 0 链接 / 66339801 bytes。派生分析：`benchmarks/analyses/cpp-build-rtorrent-common-canary-v2-results.json`。

会话：`/home/yiwei/.codex/outputs/forge-rtorrent-real-session-2026-10-21/`。`independent-real-audit.json` 以独立 stdlib 实现核验全量清单、Git release 组件与父链、实际请求三级可逆材料、原响应逐项 Token/费用/身份/生命周期、作者源码及未观察层，结果 valid。`independent-runtime-audit.json` 核验三个实际 compile 镜像、1010:1010、2CPU、禁网和临时 Git 配置，六个 ID/name 实际不存在，daemon 可达，结果 valid。审计初版将模型侧文件边界摘要误当完整策略、第二版误用排序 JSON 指纹；两份失败实现、日志及勘误均保留，最终按原协议字段顺序计算指纹，raw 未改。

验证：30 项授权与相邻回归通过（含第十三请求实际准入及 step 先触发）；产品 2455 passed / 44 skipped / 27 warnings；Ruff 和 613 后端文件格式检查、完整候选 CLI 免费校验、Docker 入口检查通过。历史 pytest 临时目录权限告警原样保留。最终结果提交须三项 CI 成功后仅合科研依赖分支，发布状态以 GitHub 和会话 final-publication-audit.json 为准。

## 解释与下一阶段

这批证据首先定位了原单响应脚本资格未覆盖的多轮材料问题，以及模型规划中的重复读取。它不能排名三策略构建能力、证明规划无收益或主线没有论文价值；也不能将尚未执行的作者测试和交付写成失败。已有工程资格仍证明参考方案能够满足原完整任务，但不代替真实模型结果。

下一阶段 #591 为免费工程修复与资格：在原 50k/8k、任务和裁判不变的条件下，核验相同 JSON 值的可逆共享表示及实际多轮 middleware。会话中的后验原型只把两个停止包离线重建至 48475/48877 bytes，未发送 Provider，不是正式资格或真实模型成功。须逐值还原、拒绝损坏引用，覆盖 28 个实际请求和两个停止包；资格后才冻结独立新版本 canary。旧 v2 失败不回填，不把前后工程版本差当因果收益。新付费阶段如启动，仍共享原用户授权、已花费用和绝对截止；无自动重试。
