# 动态预算多步轨迹 benchmark 跨系统语义资格 v4 预注册

v3 完整通过 CMake 和 Make 两个项目 block：6 个项目、18 个状态、36 次 continuation、两个 stop reservation 转移均通过。随后 `autotools-libestr/configure` 的两次 continuation 都 exit 0，声明的 `config.status` 与 artifacts hash 相同，唯一 workspace 差异为 `autom4te.cache/requests`。该目录是 Autoconf/Automake 的再生成缓存，不是 configure 的权威输出。v1 至 v3 evidence 和停止决定保持只读。

v4 是本阶段最后一个 qualification amendment。在任何新运行前固定：决策相关 workspace hash 排除路径组件名为 `autom4te.cache` 的整棵缓存目录；checkpoint tar 和 raw evidence 仍完整保留该目录。v4 继承 v3 的固定 state hostname、v2 的四个诊断日志排除项，以及 v1 的全部项目、动作、预算、转移与停止条件。

v4 若出现任何新的退出失败或 successor 差异，本阶段立即停止，不再新增 normalization amendment。全部门槛通过时，决定仍只授权设计 Agent continuation 资格，不授权 Provider 调用或 controller 实现。
