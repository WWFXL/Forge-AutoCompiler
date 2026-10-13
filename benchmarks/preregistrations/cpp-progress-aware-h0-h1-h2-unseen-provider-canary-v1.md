# C++ H0/H1/H2 未见项目族 Provider Canary v1 预注册

## 身份与授权

- Identity：`cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1`
- Tracking Issue：#447
- Branch：`yiwei/447-h0-h1-h2-unseen-provider-canary`
- Parent：`cpp-progress-aware-h0-h1-h2-unseen-qualification-v1`
- 工作类型：正式 canary 数据采集与工程资格；不是 treatment-effect 实验

研究负责人已在当前会话授权进入下一阶段并持续执行至关键结论。Q0 前禁止读取 credential 或调用 Provider；Q0 通过且
冻结 release 已推送后，允许读取 `DEEPSEEK_API_KEY`、调用 DeepSeek、使用 Docker 并写入本 identity 的 create-once
evidence。旧 identity/evidence 只读；replacement、backfill、失败重跑、删除失败 observation、动态预算 controller 和 Jev
调用均未授权。

## 样本与三臂

- `cmake-tinyxml2@8224e427b655b83dae5e2298f1e6919523a78737`
- `make-mjson@696969cd0d35399cc66075f5ec7a96e23ba4a89b`
- `autotools-libcsv@b1d5212831842ee5869d99bc208a21837e4037d5`

H0/H1/H2 分别绑定 Runtime v3/v4/v5。顺序为 tinyxml2 `H0,H1,H2`，mjson `H1,H2,H0`，libcsv
`H2,H0,H1`。每臂从 parent 冻结 source archive 建立独立离线 Session。

## Provider、预算和停止

Provider/profile/actual model 固定为 DeepSeek `deepseek-flash`；endpoint `https://api.deepseek.com`；非流式、thinking
关闭、模型重试 0。每臂 36 requests、600,000 recorded-token 停止阈值、100,000 单响应上界、700,000 授权上界，
96 steps、72 tools、48 commands。九臂总上界为 324 requests、6,300,000 recorded tokens 和 `$7.56`。

usage 缺失或不守恒、单响应越界、整批授权越界、identity/release/source/image 漂移、未清理资源或 infrastructure error
均 fail closed。已声明 arm 不得 retry；部分结果必须保留。

## Canary 资格判据

必须同时满足：9/9 分类终结；request lifecycle 与 usage 完整；预算守恒；source/release/image/动作后观察绑定；9/9 cleanup；
H0/H1/H2 instrumentation 可区分；H2 至少一次 replay closure；每个 treatment 至少一个 candidate 进入完整六层 evaluator；
整批不越过授权上界。

通过决定为 `proceed_to_unseen_three_arm_formal_comparison_design`，失败决定为
`stop_before_unseen_three_arm_formal_comparison`。Strict success、Token、费用、replay rejection 与墙钟仅作描述性规划，
不形成 canary treatment effect。正式 18-arm 比较若获准必须使用新的 identity，且不合并本 canary observation。
