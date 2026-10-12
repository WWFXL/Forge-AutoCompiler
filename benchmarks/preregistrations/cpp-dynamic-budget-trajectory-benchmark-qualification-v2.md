# 动态预算多步轨迹 benchmark 语义等价资格 v2 预注册

v1 在首个 `cmake-spdlog/configure` 状态按规则停止。两次 continuation 均 exit 0，声明的 `CMakeCache.txt` 与 artifacts hash 相同；唯一 workspace 内容差异是 `build/CMakeFiles/CMakeConfigureLog.yaml` 中由 CMake/GCC 自动生成的 `TryCompile-*`、`cmTC_*` 和 `/tmp/cc*` 诊断名称。v1 evidence、marker、inventory 和停止决定保持只读。

v2 在任何新 continuation 运行前固定以下唯一 amendment：

- checkpoint tar、stdout/stderr 和全部原始 workspace 文件仍完整保留；
- successor 的**决策相关 workspace hash**忽略文件名恰为 `CMakeConfigureLog.yaml`、`CMakeOutput.log`、`CMakeError.log` 或 `config.log` 的构建工具诊断日志；
- 退出码、声明产物 hash、artifacts tree hash、其他 workspace 文件及其可执行位仍必须完全一致；
- 不使用正则改写内容，不忽略 build artifact，不新增事后白名单；首次剩余差异仍立即停止；
- 项目、exact commit、动作、顺序、预算、重复数和所有其他门槛逐字继承 v1；使用全新 create-once evidence root。

这些诊断日志可以影响后续 Agent 的文本输入，因此不能从 checkpoint 或 evidence 删除；它们只是不参与“两个 action 是否得到同一决策状态”的 content hash。未来若研究日志语义，必须从原始文件单独提取稳定字段。

通过决定仍为 `proceed_to_agent_continuation_qualification_design`，只允许设计独立 Agent continuation 资格；失败仍为 `stop_before_agent_continuation_and_controller_implementation`。本 identity 继续保持 0 credential、0 Provider、0 Agent 和 0 controller implementation。
