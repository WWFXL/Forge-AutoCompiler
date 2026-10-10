# Jev 未见项目族正式三臂比较 v3 资格失败

- 决定：`supersede_with_fresh_v4_identity_and_replace_incompatible_case`
- 阶段：零 Provider qualification
- 完成：前 `6/12` 个项目均通过 S0-S5 和 clean replay
- 停止：第 7 项 `ffmpeg` 被严格 CandidateVerifier 以 `build_system_mismatch` 拒绝
- Provider / credential / formal attempt：`0 / 0 / 0`

v3 已正确恢复 tracked `Makefile`；修复后的 `make -j4 ffmpeg` 和产物暂存均返回 0。
失败发生在候选提交：初始探测同时发现 `make` 与 `autotools` 并按协议选择 `make`，但严格
verifier 会把成功的 `./configure` 后接 `make` 解释为 Autotools 执行，因此拒绝候选。该失败是
冻结样本与既有构建系统身份证明规则不兼容，不能评价 Jev、Agent 或 treatment effect。

不放宽 verifier、不伪造命令角色，也不修改共享裁判。v4 使用新的未见项目族
`bellard/quickjs@9d01a96849dbbe653da65f231cd40bddc7457ae2` 替换 FFmpeg。该提交晚于冻结
cutoff；固定镜像内 `make -j4 qjs` 与功能探针通过，源码快照 SHA-256 为
`320a80d616dede86413c8aecc46d665e971f0bf55eec414599d795917c537def`。替换仍保持
CMake/Make/Autotools 各 4 项、`dependency/configure/build` 各 4 项。

失败项与前六项均已终结且无受管资源；正式 evidence root 和资格报告均未创建。v3 不续跑、
不 backfill；v4 从 12 项资格门禁重新开始。
