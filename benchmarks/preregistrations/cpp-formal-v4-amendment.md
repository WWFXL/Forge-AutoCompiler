# C/C++ formal v4 协议修订预注册

状态：未授权采集。Issue #103 只冻结协议、实现门禁、运行测试和非模型 preflight；不得执行 provider canary、创建 physical-attempt ledger 或调用模型。

## 修订依据

formal v3 首批在 7/10 个授权 slot 后达到 recorded-token 边界。7 个 slot 共调用 Compiler 14 次；其中 PowerDNS 单槽调用 4 次 Compiler，总历时 3,240.758 秒。现有 900 秒限制作用于每次 Compiler 调用，不能限制整个 physical attempt 的时间和请求尾部。

## Attempt 级预算

| 门禁 | v4 冻结值 | 依据 |
| --- | ---: | --- |
| physical attempt 总墙钟 | 1,800 秒 | v3 正常成功槽约 149-250 秒，失败槽约 1,037-3,241 秒；保留复杂 case 空间并截断极端尾部 |
| cleanup reserve | 120 秒 | 从总墙钟中预留，达到 1,680 秒后不得开始新的 provider、Compiler、submit 或 replay 工作 |
| Compiler 调用总数 | 2 次 | v3 正常成功槽为 1 次；4 次调用造成单槽长尾，2 次允许一次受控恢复 |
| 模型请求总数 | 48 次 | v3 正常成功槽为 8-11 次；失败长尾为 67-72 次 |

预算必须在 provider 请求、Compiler 调用、submit/replay、finalize 和 cleanup 前复算。新工作超限时终态分类固定为 `attempt_budget_exhausted`；finalize 和 cleanup 不因超限而跳过，超出总墙钟必须记录为 overrun。

当前 v4 runner 只开放预算状态复算与 checkpoint 拒绝函数。由于 `collection_authorized=false`，所有真实执行入口都在 ledger 和 provider 调用前拒绝。后续若创建 authorized v4，必须把同一 checkpoint 函数接入实际执行路径并增加取消、finalization 和 orphan reconciliation 的真实 Docker 回归，不能仅解除授权位。

## 宿主资源门禁

创建新 attempt 前必须同时满足：

- `/proc/meminfo` 的 `MemAvailable` 不低于 2 GiB；该值代表 LangGraph 所在 WSL2 Linux 环境可见的宿主内存余量。
- `docker info` 在 10 秒命令时限内成功。
- Docker daemon 响应延迟不高于 5 秒。
- 既有 Compose/DooD、Docker socket、解释器、runtime import、evidence bind source 与可写目录门禁继续通过。

preflight 只记录可用内存字节数、阈值和 daemon 延迟，不记录 IP、SSID、代理、凭据、Docker server 版本或其他宿主标识。

## 不平衡样本处理

- formal v3 的 7 个 slot 保持独立描述性 protocol stratum，不删除、不回填，也不与 v4 primary estimand 池化。
- v4 primary estimand 只使用 v4 下完成的完整 project block。
- token 或资源停止造成的不完整 block 不进入 paired primary estimate，但保留在端到端描述性失败分母和 provider/case imbalance 报告中。
- 禁止 retry、fallback、replacement 和 backfill。
- v4 的采集范围、批次 token 上限和启动时间必须在独立 Issue 中重新获得实验负责人确认。

## 研究边界

本修订针对的是实验运行控制与删失机制，不改变 C/C++ 样本框、exact commit、构建路径、模型条件、Compile Session、clean replay 或 artifact oracle。阈值来自 formal v3 的小样本运行证据，属于预注册工程参数，不应被解释为总体最优值；后续论文应将阈值敏感性列为限制或消融项。
