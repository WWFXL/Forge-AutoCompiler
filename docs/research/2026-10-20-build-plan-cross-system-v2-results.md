# 跨系统真实走读 v2：Make闭合，Autotools恢复工程停止

Issue #478；独立身份 `cpp-build-plan-cross-system-v2`。zstd真实规划1次请求后，经原始make check、精确libzstd.a、clean replay、重放测试和cleanup，Session completed。支持已见Make开发项目的模型规划到严格交付链路接入；与此前cJSON一起仍不是总体或方法效果证据。

libusb初始方案完成依赖/配置/编译，固定make check的stress_mt失败后进入恢复。恢复响应为18,239 input + 32,768 output = 51,007 recorded tokens，输出全部为reasoning、finish_reason=length、无方案，同时超过冻结50,000单响应合同。计量先保存响应和usage，再按AgentWorkflowBudgetExceeded停止，未追加请求，Session failed并清理。不能将其写成该故障不可修或选择方法负结果，也不能在原身份提高阈值继续。

v2共3请求、43,814 input、43,357 output，共87,171 recorded tokens，已知公开峰时价保守估算$0.2295282，0未知usage。v1+v2共6请求、152,415 tokens、$0.3727878；另为初始旧live测试未知费用保留$1，所以共享额度已知估算+保留为$1.3727878。预留不等于实际账单；历史cJSON费用不计入本次新增额度。

原始 `/home/yiwei/.codex/outputs/forge-cross-system-model-v2/`，1997 files / 179,476,348 bytes，inventory canonical SHA-256 `da8ef3673980b6f3247b48f0198b69c1a6e8c70575194cbe3e504c08333db4d6`。独立审计 `forge-continuous-research-2026-10-19/cross-system-v2-audit.json`：inventory有效、请求响应和usage守恒、两项目cleanup成功；libusb明确记录单响应合同超限。证据完整不代表该arm满足运行预算合同。

manifest `benchmarks/manifests/cpp-build-plan-cross-system-v2.json` SHA-256 `1b6fc08f6536106fed161cde86a4aabdf534217ac016bd24a22117dd1810b6c0`；对应预注册、运行源码快照、原始诊断、方案和日志保留。

决定：结束此已见开发走读，不继续在libusb上追加付费重试。下一独立设计需让消息、schema、max_output与单响应recorded-token设计上界一致，并在源码和真实oracle资格已闭合的新开发任务上做公平canary。不得回填v1/v2、降低测试或以恢复未完成推断模型能力不足。
