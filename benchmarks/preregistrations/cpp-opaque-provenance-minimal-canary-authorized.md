# Opaque build provenance 最小 canary 授权候选与零 provider 接线门禁

本协议承接 Issue #180 的未授权最小 canary 候选。Issue #182 只授权实现版本化 runtime adapter、冻结 evidence identity 和执行 0-provider preflight；不授权读取 AK、创建模型客户端、发送 reachability 请求或运行 baseline/treatment pair。

## 父协议与研究单位

父身份固定为 `main@06ba008ddaa77956ce39e97f30f79e27a1a0639e`、manifest canonical SHA-256 `ad5a1ac989c4072ec097a3b0949d5e4393475d6df0896e108dbc313690dd3ee7`。Case、provider、预算、顺序、停止规则和分析边界逐字段继承父协议，不在本阶段改写。

研究单位仍是单个 `cppitertools` opaque-provenance checkpoint pair，顺序固定为 `baseline -> treatment`。该单 pair 未来只验证机制接线，不能估计 treatment effect、计算 p 值或排名模型。

## Evidence identity

独立逻辑目录固定为 `/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-minimal-canary-authorized-v1`。其 preflight snapshot、reachability marker、pair ledger 和 canary report 路径全部进入 canonical evidence identity；marker 在请求开始时即消耗机会，文件只能 append/create-once，不得覆盖历史 evidence。

本阶段 preflight 不写 evidence。目录必须不存在或为空，managed `deerflow-compile-*` / `deerflow-replay-*` orphan 必须为 0。

## Runtime preflight

只读 snapshot 必须证明：

1. 当前分支为干净 `main`，`HEAD == origin/main`，且 #180 baseline 是 HEAD 祖先；
2. Docker provider 为 WSL Ubuntu-native、context 为 `default`、endpoint 为 `/var/run/docker.sock`；
3. 网络介质记录为 `wired`、`wifi` 或 `mobile_hotspot`，不记录 SSID、IP、运营商账户或凭据；
4. 冻结 evidence 目录为 0 条目，managed orphan 为 0。

Runtime adapter 只允许 `validate`、`plan` 和 `preflight`。`execute_reachability` 与 `execute_canary` 必须机械拒绝；源码不得读取 credential 或创建 provider model。

## 下一授权门禁

本协议合并并从干净主干完成真实 0-provider preflight 后，只形成一次真实授权的决策包。若实验负责人明确授权，下一版本才可增加一次 reachability 与固定单 pair execute path，并在请求开始前创建不可变 marker。未经该授权不得产生任何 provider/evidence 副作用，也不得扩大 behavioral pilot。
