# Stage C v7 pre-freeze verifier canary 候选预注册

日期：2026-09-27。追踪：[Issue #341](https://github.com/WWFXL/Forge-AutoCompiler/issues/341)。

## 目的

Stage C v6 离线重评留下四条候选合同失败：`theora-r1` 的未声明静态库和零字节文件、`json-c-r2` 的错误 target mapping 与不完整头文件闭包、`libjpeg-turbo-r2` 的过宽安装集合，以及 `oatpp-r2` 的未声明测试库。Runtime v3 已在 candidate create-once 持久化前加入完整交付、唯一 target 和受信功能检查，并允许 Agent 在同一 attempt 内修复后重提。

v7 候选用于冻结首次真实验证该反馈闭环的独立 canary identity。它不修改、不续跑也不回填 v5/v6 identity 或 evidence。

## 固定 canary

按以下顺序固定四个 Forge B 臂 attempt，每个 task 只执行一次：

1. `theora`：未声明 compiled artifact 与零字节 delivery。
2. `json-c`：非唯一 target mapping 与公共头文件闭包。
3. `libjpeg-turbo`：过宽安装集合及无效 executable delivery。
4. `oatpp`：未声明测试静态库。

这些 case 用于工程 canary，不构成 A/B 比较，不估计 treatment effect、总体成功率或任务集外泛化。四个 attempt 使用新的 ID、thread、session 和 evidence 目录；历史候选只用于冻结 case 来源，不作为新结果输入。

## 运行链路

- Forge 方法固定为 `agent-workflow-runtime-v3`。
- 每次 candidate submit 先运行完整 `/artifacts` 扫描、唯一 target mapping 校验和 system-owned functional oracle。
- 拒绝 evidence 最多返回 12 条排序去重的路径或值，不返回 oracle 原始输出。
- Agent 可在同一 attempt 内修复并重提；candidate 仍只能 create once。
- candidate 冻结后必须由 external evaluator v4 独立执行 S0-S5、功能 oracle、clean replay、bitwise delivery 比较与 cleanup。
- 任一 canary 失败立即停止；不重试、不替换、不回填。

## Token 与操作边界

- `max_recorded_tokens`、reachability token 上限和阶段累计 token 上限均为 `null`。
- 每次 Provider 响应必须记录 input、output 和 total token；累计 token 不触发终止。
- 每个 attempt 的请求数、Agent step、工具调用、命令数和墙钟门禁继续生效。
- 当前候选阶段不读取凭据、不创建模型、不调用 Provider、不启动正式 Docker canary、不注册 attempt，也不写正式 evidence。

## 通过条件

未来 authorized identity 必须逐 attempt 记录 pre-freeze 提交次数、拒绝代码、拒绝 evidence 数量、是否同 attempt 修复、最终 candidate identity、S0-S5、bitwise replay、token ledger 和 cleanup。canary 只有在 candidate 冻结、external evaluator v4 全层通过、finalize 成功且 managed container/image 为 0 时才通过。

本候选合并后仍不能直接执行。真实 Provider canary 必须从干净主干派生新的 create-once authorized identity，并重新冻结 release revision、协议、runner、manifest 和 evidence 路径。
