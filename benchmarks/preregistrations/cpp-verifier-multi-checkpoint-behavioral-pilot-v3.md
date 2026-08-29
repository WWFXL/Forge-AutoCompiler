# 多 checkpoint behavioral pilot v3 未授权预注册

本协议承接 Issue #168 的三构建系统零 provider 门禁和 Issue #170 的协议冻结授权。当前版本只冻结实验身份与 runner 适配边界，不授权读取 AK、调用 provider、创建 formal physical attempt 或写入真实 evidence。

## 研究问题与实验单位

研究问题保持为：在同一个 `artifact_staging_missing` actionable failure checkpoint 上，向 compiler continuation 提供白名单结构化 verifier repair packet，是否比 baseline 原始反馈提高 candidate verification 与 clean replay 的配对 conversion。

实验单位是 failure checkpoint case，不是单个随机重复。三个 case 固定为：

- `cppitertools@531b3d7`：CMake，可执行文件；
- `janet@c0b32d4`：Make，静态库；
- `libcheck@11970a7`：Autotools，静态库。

三者的仓库、提交、命令、依赖、产物和 controlled fault 身份只从 `cpp-verifier-multi-checkpoint-zero-provider-gate.json` 读取，并同时校验 canonical 与文件 SHA-256。不得把历史自然失败 fixture 伪装为可续跑 checkpoint。

## Schedule、provider 与预算

- 每个 case 固定 2 pair：一个 `baseline -> treatment`，一个 `treatment -> baseline`；共 6 pair / 12 arm。
- provider identity 延续 behavioral v2：DeepSeek `deepseek-v4-flash`、`https://api.deepseek.com`、300 秒 timeout、0 retry、非 streaming、禁止 fallback。
- 每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间加 120 秒 cleanup reserve、120,000 recorded tokens。
- 每对机械上限 240,000 recorded tokens，阶段总机械上限 1,440,000。约 231,944 tokens 仅是资源规划估计，不是停止阈值。

当前 manifest 的 provider 字段只是未来授权身份，不构成真实请求许可。runner 只有 `validate`、`plan` 与 `show-pair`，任何 collection 入口必须 fail closed。

## 终态与停止规则

沿用 behavioral v2 的三层终态：`infrastructure`、`model_behavior` 与 `verification_outcome`。合法 endpoint timeout 记为删失，已分类模型行为失败保留为 outcome；identity、evidence、预算、cleanup 或无法分类的基础设施失败立即停止 batch。

禁止 retry、replacement、backfill、schedule extension 和第 7 个 pair。不得修改或回填 behavioral v2 与零 provider gate 的冻结 evidence。

## 分析契约

每个 case 独立报告：

1. baseline/treatment 配对四格；
2. 请求数与 recorded tokens；
3. failure transition；
4. 两个 pair 的顺序与三层终态。

跨 case 只使用三个 case 等权的 macro-average，每个 case 权重固定为 `1/3`。不能把 6 个 pair 平铺为 6 个独立 failure contexts；不计算 p 值、不池化 provider、不做模型排名，也不与历史 v2 pair 池化。

## 下一授权门禁

只有本协议、Schema、runner plan、定向 pytest、Ruff 和 CI 全绿并合并到 `main` 后，才能建立新的中文采集 Issue 与授权 manifest。真实采集仍需先核对 Ubuntu 原生 `docker.service`、干净 `main == origin/main`、网络介质、provider identity、预算与 0 managed orphan。
