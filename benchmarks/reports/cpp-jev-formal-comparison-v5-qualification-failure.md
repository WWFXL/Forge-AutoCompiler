# Jev 未见项目族正式三臂比较 v5 资格失败

- 决定：`supersede_with_fresh_v6_identity_and_preseed_deterministic_redis_header`
- 阶段：零 Provider qualification
- 严格成功：`11/12`
- Provider / credential / formal attempt：`0 / 0 / 0`
- cleanup：`12/12` 调用成功，最终受管资源为 `0`

v5 的 WolfSSL 修复通过 S0-S5，证明排除唯一空占位头文件后，其静态库、281 个非空交付文件、
功能 oracle、provenance 和 clean replay 均能闭合。唯一失败仍为 Redis 的 S5。

Redis 的剩余问题来自故障轨迹。受控错误 target `make forge_probe_7b92e1` 会先生成
`src/release.h`；该脚本只用 Git SHA 和 dirty 状态判断 header 是否最新。后续修复构建虽然设置
`SOURCE_DATE_EPOCH`，但不会刷新已经存在的 hostname/time build ID。clean replay 不包含失败命令，
因此生成另一份确定性 header，最终产物大小、SHA-256 和版本输出均不一致。

保留完整 Git 元数据与 Forge safe-directory 条件的隔离验证表明：若在共享 configure 阶段先以冻结
`SOURCE_DATE_EPOCH` 生成 `src/release.h`，则经历错误 target 的 candidate 与不经历失败命令的 replay
最终得到相同的 `redis-server` SHA-256 和 build ID。

v6 只给 Redis 的 configure 合同增加上述确定性 header 生成命令；v5 已通过的 WolfSSL 修复及其余
10 个项目、三臂、顺序、模型、阈值、预算、统计和停止规则均保持不变。v5 原始报告保持只读，
不续跑、不 backfill；v6 从 12 项资格门禁重新开始。
