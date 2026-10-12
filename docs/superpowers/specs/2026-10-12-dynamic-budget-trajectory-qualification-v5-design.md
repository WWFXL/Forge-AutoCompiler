# 动态预算轨迹 benchmark 资格 v5 设计

> 日期：2026-10-12
> Tracking Issue：[#427](https://github.com/WWFXL/Forge-AutoCompiler/issues/427)
> 工作类型：零 Provider benchmark 资格数据采集

## 1. 研究问题

在 Issue #425 修复 checkpoint 合法相对符号链接恢复后，同一冻结 schedule 是否能在 CMake、Make、Autotools 上形成完整、可重复、预算守恒的多步轨迹 benchmark，为下一阶段 Agent continuation 资格设计提供基础？

本阶段不评价动态预算 controller 的策略效果。它只验证未来控制器所需的状态恢复、动作后观察和资源计量是否在三个构建系统上闭合。

## 2. 冻结输入

- Identity：`cpp-dynamic-budget-trajectory-benchmark-qualification-v5`；
- Docker image：`autocompiler:gcc13@sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`；
- CMake、Make、Autotools 各 3 个项目，共 9 个未见项目族；
- 每项目 3 个连续状态，每状态从同一 checkpoint 执行 2 次禁网 continuation；
- 总计 27 个状态、54 次 continuation；
- 每个构建系统共享 900,000 ms、18 次 build execution 的 block 预算，Provider 四维预算均为 0；
- 第三个项目的 300,000 ms、6 次执行配额由显式 stop reservation 转移获得。

项目、exact commit、动作命令、声明输出、预算和资格门槛与 v4 相同。v5 继承固定 continuation hostname、四类非权威诊断日志排除以及 `autom4te.cache` 决策哈希排除；完整 checkpoint tar 不删除这些内容。

## 3. 恢复语义

v5 的 `_restore_snapshot` 使用 `forge_checkpoint_archive.restore_checkpoint_archive`：所有成员继续经过标准 `tarfile.data_filter`，symlink 按成员父目录解释，hardlink 按 archive root 解释，特殊文件与越界链接被拒绝。恢复先写入同级 staging，完成全树 containment 后才原子发布。

Checkpoint 继续绑定 source、image、workspace snapshot、artifacts snapshot、message 和 budget 哈希。两次 continuation 都从同一份只读 snapshot 恢复；任何恢复失败都属于本 identity 的真实停止结果。

## 4. 通过门槛

必须同时满足：

1. 9/9 项目和 27/27 状态完成；
2. 54/54 continuation exit 0；
3. 27/27 状态的两次 successor 决策状态一致；
4. 27/27 checkpoint 绑定、预算守恒和动作后权威观察闭合；
5. 3/3 build-system block 的 stop reservation 转移通过；
6. Provider requests、Agent calls 和 credential reads 均为 0；
7. cleanup 后受管容器为 0。

全部通过才决定 `proceed_to_agent_continuation_qualification_design`。任一新退出失败、successor 差异、预算不守恒、恢复失败或资源残留都决定 `stop_before_agent_continuation_and_controller_implementation`。

## 5. 证据与边界

v5 使用独立 create-once evidence root，不续跑、补齐、替换或修改 v1-v4。运行前冻结 manifest、预注册和 runner；只允许一个正式 attempt。出现新失败后不增加 normalization amendment。

通过只说明多步轨迹 benchmark 基础合格，不说明动态预算策略优于固定预算，不说明 Jev 或 Agent 有效，也不支持自然失败或开放世界外推。
