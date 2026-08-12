# Forge C/C++ formal v4 Ubuntu daemon gate and initial-block decision

## 状态与边界

- 状态：结果盲态设计候选，等待实验负责人确认。
- 本文不授权 provider canary、physical attempt、batch 或模型调用。
- formal v1-v4 runtime candidate、v3 的 7 个 ledger 和所有历史 evidence 保持不变。
- v3 slot 8-10 不创建；v3 与本候选不进入同一个 primary estimate。

## 固定运行环境

- Windows 仅为物理宿主机。
- Forge 的 Compose/DooD 控制面、Compile Session 和 clean replay 只使用 WSL2 `Ubuntu` 发行版内由 `docker.service` 管理的原生 Docker Engine。
- Docker context 固定为 `default`，socket 固定为 `/var/run/docker.sock`，daemon provider 固定为 `ubuntu-native`。
- Docker Desktop 是独立 daemon，不作为启动、诊断或故障回退路径；门禁失败时停止并请求用户恢复 Ubuntu 服务。
- formal preflight 只记录 provider 分类和布尔检查，不记录主机名、IP、代理、凭据或原始 daemon 标识。

## 首批完整 project block 建议

- 选择规则：冻结 schedule 中第一个项目，不依据 v3 结果选择。
- 项目：`cppitertools`。
- 完整 block：两个 condition 各三次重复，共 6 个 physical attempt。
- 保留原 schedule identity：`1, 2, 73, 74, 153, 154`；不把它们改写成新的连续 slot。
- 两个 condition 保持 `richlab-gpt-5.5` 与 `deepseek-v4-flash`，禁止 fallback、replacement、retry 和 backfill。

## 预算与停止条件

- 单个 physical attempt 继续使用 1,800 秒总墙钟、120 秒 cleanup reserve、最多 2 次 Compiler 调用和 48 次模型请求。
- 首批最多 6 个 attempt；attempt 墙钟上界合计 10,800 秒，不含人工等待。
- recorded-token 上限建议为 980,000。计算依据是正式预注册的 29,396,970 contingency tokens 按 30 个项目线性分摊后向上取整，不使用 v3 单项目结果调低预算。
- token 边界只在当前 attempt 终结、finalize、cleanup 和 orphan reconciliation 完成后，于创建下一 attempt 前检查，因此最后一个 attempt 可能产生有限越界；不得中断 cleanup 来硬截 token。
- 任一 runtime preflight、双 provider canary、daemon provider、ledger hash chain、Session finalization 或 cleanup/orphan 不变量失败时停止。
- 若 token 边界导致 block 未完成，所有 attempt 保留在端到端描述性分母，但该 block 不进入 paired primary estimate。

## 下一授权动作

实验负责人需要单独确认：一个完整 block、6 个指定 schedule slot、980,000 recorded-token 上限，以及上述停止条件。确认后才创建新的中文授权 Issue 和 authorized identity，并在首条 ledger 前执行宿主门禁、Compose/DooD runtime preflight 与一次双 provider canary。
