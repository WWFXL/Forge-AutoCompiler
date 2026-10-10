# Jev 未见项目族正式三臂比较 v4 资格失败

- 决定：`supersede_with_fresh_v5_identity_and_repair_two_project_contracts`
- 阶段：零 Provider qualification
- 严格成功：`10/12`
- Provider / credential / formal attempt：`0 / 0 / 0`
- cleanup：`12/12` 调用成功，最终受管资源为 `0`

v4 的 12 个项目均完成故障注入、代码绑定动作、产物暂存和候选提交。CMake 四项、Make
前三项和 Autotools 前三项通过 S0-S5；失败只出现在 Redis 与 WolfSSL，不能评价 Jev、Agent
或 treatment effect。

Redis 的 candidate 与 clean replay 均成功构建并通过功能探针，但 `src/mkreleasehdr.sh` 在
`SOURCE_DATE_EPOCH` 未设置时把容器主机名和当前时间写入 build ID。两次产物大小相同，SHA-256
与 `--version` build ID 不同，因此 S5 以 `replay_artifact_invalid` 拒绝。隔离诊断中固定
`SOURCE_DATE_EPOCH` 后，两次独立 clean build 的二进制 SHA-256 与版本输出完全一致。

WolfSSL 的静态库、功能 oracle、provenance 和 Forge clean replay 均通过，但递归暂存的 282 个文件
包含唯一的 0 字节占位文件 `include/wolfssl/wolfcrypt/fips.h`。external evaluator 因此在 S2/S5
拒绝。隔离诊断排除该占位文件后保留 281 个非空文件，静态库哈希不变，功能编译与运行探针通过。

v5 只修改这两个项目的合同：Redis 构建命令固定 exact-commit 时间，WolfSSL 暂存时排除唯一空占位
头文件。其余 10 个项目、三臂、顺序、模型、校准、预算、统计和停止规则保持不变。v4 原始资格报告
保持只读，v4 不续跑、不 backfill；v5 从 12 项资格门禁重新开始。
