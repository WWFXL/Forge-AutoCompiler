# Opaque build provenance 最小 provider canary 候选协议

本协议承接 Issue #174 的 P2 reference contract、Issue #176 的合成 lifecycle contract 和 Issue #178 的真实 Ubuntu-native Docker lifecycle。Issue #180 只授权冻结候选协议及其零 provider 校验，不授权读取 AK、创建模型客户端、发送 reachability 请求、执行 canary 或产生正式实验 evidence。

## 研究问题与解释边界

候选 canary 研究结构化 verifier repair packet 能否在同一个 opaque build provenance failure checkpoint 上支持 baseline/treatment 双臂的真实 continuation 接线。本阶段只验证机制与证据路径，不估计 treatment effect，不计算 p 值、不排名模型，也不与历史 pair 池化。

实验单位固定为一个 `cppitertools@531b3d753d2bbfe3b0ababe61c2e95e965c54a66` checkpoint pair。父状态的 artifact 正确，但 trusted command chain 只有 opaque wrapper，production classification 为 `build_system_unproven`，P2 reference outcome 为 `opaque_build_provenance / opaque_wrapper`。

## 双臂、provider 与预算

- 顺序固定为 `baseline -> treatment`，两臂从同一个 committed message/environment/budget checkpoint 派生。
- Treatment 唯一额外 exposure 是 Issue #178 已验证的白名单 repair packet；不得泄露完整命令、argv、shell、prompt、solution 或 secret。
- 未来运行身份固定为 DeepSeek `deepseek-v4-flash`、`https://api.deepseek.com`、300 秒 timeout、0 retry、非 streaming、禁止 fallback。
- 每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间和 120 秒 cleanup reserve。
- 每臂最多 120,000 recorded tokens；一次 reachability 上限 5,000，pair 上限 240,000，阶段机械上限 245,000。

当前 provider 字段只是未来运行身份，不构成请求授权。reachability、provider call、formal attempt、canary collection 与 model token 授权全部保持关闭。

## 停止规则

未来若获独立授权，reachability 失败应在 pair 前停止。Identity、evidence、预算、cleanup 或未分类基础设施失败立即停止；合法 endpoint timeout 记为 arm 删失并继续另一臂，已分类模型行为失败保留为 outcome。禁止 retry、replacement、backfill、schedule extension 和第二个 pair。

## 零 provider preflight

协议合并后，从干净主干只读核对：

1. `main == origin/main` 且工作树干净；
2. Docker provider 为 WSL Ubuntu 原生 `docker.service` 和 `/var/run/docker.sock`；
3. 记录网络介质，但不记录 SSID、IP 或账户信息；
4. 候选 evidence 目录为空；
5. Forge managed container orphan 为 0。

该 preflight 不读取 `DEEPSEEK_API_KEY`，不调用 provider，不产生 attempt/evidence。真实 reachability 与单 pair canary 必须由后续中文 Issue 明确授权。
