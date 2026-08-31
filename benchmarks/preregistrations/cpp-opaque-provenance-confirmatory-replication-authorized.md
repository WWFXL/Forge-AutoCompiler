# Opaque provenance independent replication authorized amendment

- GitHub Issue：[Issue #247](https://github.com/WWFXL/Forge-AutoCompiler/issues/247)
- 授权基线：`main@d3b25da4d8e95d781828ac367929741fd82c4a41`
- 父候选：Issue #243 independent replication candidate
- 前置门禁：Issue #245 lifecycle zero-provider gate

## 授权

本 amendment 授权 DeepSeek OpenAI-compatible endpoint 的 `deepseek-v4-flash`：唯一 reachability request，以及 reachability 通过后的完整 6 cases / 12 pairs / 24 arms。Credential 只允许从 `DEEPSEEK_API_KEY` 环境变量读取；值不得进入 manifest、日志、报告、GitHub 或知识库。

请求 timeout 固定 300 秒，retry 为 0，fallback 禁止。Reachability 成功或失败都消耗唯一机会。Batch maximum recorded tokens 为 2,940,000；每 arm 120,000、每 pair 240,000，并在每 pair 前和每 arm 后执行门禁。

## 执行顺序

1. 在合并后的干净 `main == origin/main` 上记录 release revision 与 Wi-Fi 网络介质。
2. 验证 Ubuntu-native Docker、Compose/DooD、0 managed orphan、candidate/lifecycle/repair adapter identity，以及正式 evidence 目录为空。
3. 只检查 `DEEPSEEK_API_KEY` 环境变量存在性，然后创建一次性 reachability marker 并执行唯一请求。
4. Reachability 通过后，按冻结 schedule 顺序执行 12 pairs；每个 pair 由 Issue #241 repair adapter 执行并冻结 outcome。
5. 只有六个 project block 全部 estimable 时才执行 two-sided exact sign-flip test。

## 不变量与停止规则

- Confirmatory v1 保持 `failed_mechanism_attempt_closed`；前三个 outcome 不导入，`gpac-rep-01` 不续跑。
- 禁止 replacement、backfill、fallback、retry、历史池化、verifier 放宽和单项目模型排名。
- Reachability、release、identity、credential-presence、Docker、orphan、cleanup 或 token 门禁失败时立即停止。
- Pair 目录已开始但缺少冻结 outcome 时禁止自动补跑；保全 append-only evidence 并另行决策。
- 每个 pair 后必须回到 0 compile/replay orphan。正式 evidence 只允许 create-once 写入新 replication 目录。
