# 动态预算多步轨迹 benchmark 资格 v5 预注册

## 身份与授权

- Identity：`cpp-dynamic-budget-trajectory-benchmark-qualification-v5`；
- Tracking Issue：[#427](https://github.com/WWFXL/Forge-AutoCompiler/issues/427)；
- 工作类型：正式零 Provider benchmark 资格数据采集；
- 授权：用户已授权本阶段持续执行至关键结论；
- Evidence root：`.compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v5`，create-once；
- Attempt 上限：1。

本阶段不读取 credential，不调用 Provider/Jev/Agent，不实现 controller，不写入任何历史 evidence。

## 冻结背景

v4 已完成 20 个状态和 40 次 continuation，随后在恢复 `autotools-libestr-state-3` 时因 Python 3.10 `tarfile.data_filter` 误拒绝合法 `src/.libs/libestr.la -> ../libestr.la` 而停止。Issue #425 的独立恢复门禁 8/8 通过，并证明 v4 `libestr` checkpoint 恢复前后完整 tree hash 与决策 tree hash 一致。v1-v4 identity、停止决定和 evidence 永久只读。

## 冻结设计

v5 完整继承 v4 manifest 的 Docker image、9 个项目及 exact commit、每项目 3 个动作、每状态 2 次同源禁网 continuation、六维预算、项目 block 共享预算和 stop reservation 转移。总 schedule 为 9 个项目、27 个状态、54 次 continuation。

Runner 继承 v4 的确定性 hostname、四类构建诊断日志排除和 `autom4te.cache` 决策哈希排除，只把 `_restore_snapshot` 替换为 Issue #425 已验证的 `restore_checkpoint_archive`。Checkpoint tar 仍保留完整文件；successor 必须从动作后的 workspace、artifacts 和声明输出重新观察。

## 主要门槛

- 9/9 项目、27/27 状态、54/54 continuation 完成；
- 54/54 continuation exit 0；
- 27/27 successor 一致；
- 27/27 checkpoint 绑定、预算守恒和动作后观察通过；
- 3/3 stop reservation 转移通过；
- 0 credential、0 Provider、0 Agent；
- cleanup 后 0 受管容器。

全部通过时决定为 `proceed_to_agent_continuation_qualification_design`。任一门槛失败时决定为 `stop_before_agent_continuation_and_controller_implementation`。

## 停止与解释规则

正式 attempt 一旦创建 evidence root 即不可替换、重试、续跑、补齐或 backfill。任何新退出失败、successor 差异、恢复异常、预算不守恒或资源残留都立即封口；不新增 normalization amendment。

通过只证明跨 CMake、Make、Autotools 的轨迹恢复和计量基础合格，不证明动态预算 controller 有效果，不评价 Jev/Agent，也不支持自然失败或开放世界结论。
