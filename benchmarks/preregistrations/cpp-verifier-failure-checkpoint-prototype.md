# Verifier failure checkpoint 非模型可行性原型

## 目的

本原型只验证一个机制前提：在 actionable `submit_build_result` 已完成、下一次模型步骤尚未开始时，SQLite checkpoint 能否保存完整消息与下一节点，并从同一个中性状态派生 baseline/treatment 两臂。

## Evidence 边界

- `slot-007-openthread.json` 与 `slot-010-mupdf.json` 只保留冻结 pilot 中可公开审计的 submit 分类、构建系统、artifact identity 和内容哈希。
- fixture 不包含真实 thread/session/attempt/command identity、provider 响应、prompt、日志、宿主路径或凭据。
- 原始 Slot 7/10 没有完整 compiler transcript，因此 fixture 不是历史运行的可续跑 checkpoint。Human/AI/ToolMessage 由确定性 fake graph 构造，只用于验证 checkpoint 契约。

## 通过条件

1. 图在 fake submit 后暂停，checkpoint 的 `next` 固定为 `continue_model`。
2. SQLite 关闭并重新打开后，两臂都能从 `continue_model` 恢复。
3. 分支前的 HumanMessage、AI tool call 与 ToolMessage identity 完整；两臂只允许 feedback content 和 arm/session identity 不同。
4. 恢复两臂不会再次执行 fake submit。
5. 全程不导入或调用 provider、Docker runtime 与 physical-attempt runner。

## 非目标

本原型不证明 workspace、容器 rootfs、预算 monotonic clock 或真实 provider client 可以恢复。只有本门禁通过后，才能单独评审 rootfs 与 bind-mount 双重恢复；未通过该后续门禁前不得创建真实 mechanism slots。
