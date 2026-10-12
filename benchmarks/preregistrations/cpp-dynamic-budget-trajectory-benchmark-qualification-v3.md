# 动态预算多步轨迹 benchmark 环境身份资格 v3 预注册

v2 完整通过 `cmake-spdlog` 的 3 个状态和 6 次 continuation，随后在 `cmake-cli11/configure` 停止。两次 CLI11 configure 均 exit 0，差异来自 Docker 自动生成的不同 hostname 被 CTest 写入 `CMakeCache.txt` 的 `SITE` 和 `DartConfiguration.tcl` 的 `Site`。这不是工具诊断噪声，而是 checkpoint 未绑定完整环境身份。v1/v2 evidence 与停止决定保持只读。

v3 在任何新运行前冻结唯一新增 amendment：所有同一 state 的 continuation 使用完全相同、由 `state_id` 派生的 Docker hostname。不同 state 的 hostname 仍不同，container name 继续唯一；image、网络、UID/GID、CPU、mount 和命令不变。

v3 逐字继承 v2 对 `CMakeConfigureLog.yaml`、`CMakeOutput.log`、`CMakeError.log` 和 `config.log` 的决策相关 hash 排除规则，以及 v1 的 9 项目、27 状态、54 continuation、预算、stop transfer、停止条件和零 Provider 边界。它使用独立 create-once evidence root。

通过仍只授权设计 Agent continuation 资格；失败仍停止在 Agent continuation 和 controller 实现前。
