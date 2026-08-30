# C/C++ opaque provenance R2 Make 一次性执行修订

状态：授权但未执行。追踪 Issue：[#208](https://github.com/WWFXL/Forge-AutoCompiler/issues/208)。

## 研究问题

在一个独立、result-blind 的 GNU Make case 上，结构化 verifier repair packet 是否能让 Agent 从同一 failure checkpoint 选择可信 direct Make 动作，并把 P2 provenance 从 `unproven/opaque_wrapper` 转为 `proven/direct_make`？

本次只采集一个 `baseline -> treatment` state-matched pair，属于跨构建系统机制复制，不估计 treatment effect、不计算 p 值、不排名模型，也不与历史 CMake pair 池化。

## 冻结 case

- Repository：`https://github.com/kjdev/hoextdown`
- Commit：`1ef9a71957570c2a65b7daa1b2f693ad87daf385`
- Build system：GNU-compatible Make
- Container workdir / effective directory：`/workspace/repo`
- Target / build output / staged artifact：`libhoedown.a`
- Artifact type：`static_library`
- Direct Make jobs：`2`

Parent 只允许由冻结的 opaque `sh -c` wrapper 创建真实产物；其顶层 trusted identity 不能证明 Make。Treatment packet 不包含命令、argv、shell 或完整解法。

## Runtime-parity

每臂动作上限固定为 inspection/build/stage/submit = `4/2/2/2`，claim 必须原子完成。合法 repair build 必须是 direct `make` 或 `gmake`，结构化解析后的 effective directory、target 和 jobs 必须分别为 `/workspace/repo`、`libhoedown.a`、`2`。Build 与 stage 必须分开，禁止 clone、configure、dependency、housekeeping、manual replay 与 compound build/stage。

所有可分类拒绝必须保留历史 `agent.tool_failed`，并以 `failure_id` 关联 `agent.tool_rejection_observed`。Companion 只记录 bounded classification、action kind、model request ID、tool ordinal 与 command SHA-256，不记录原始命令、错误文本、模型正文、工具参数或凭据。

## Provider 与预算

- Provider/model：DeepSeek `deepseek-v4-flash`
- Endpoint：`https://api.deepseek.com`
- Credential env：`DEEPSEEK_API_KEY`
- Timeout：300 秒；0 retry；非 streaming；禁止 fallback
- Reachability：最多 1 request / 5,000 recorded tokens
- 每臂：最多 8 requests、8 model turns、24 graph steps、600 秒工作时间、120 秒 cleanup reserve、120,000 recorded tokens
- Pair：240,000 recorded tokens；阶段总上限：245,000

## 执行顺序与停止规则

1. 从已合并、干净且与 `origin/main` 一致的主干运行 preflight。
2. 只使用 Ubuntu WSL2 原生 `docker.service` 的 default context 与 `/var/run/docker.sock`；禁止 Docker Desktop。
3. 在空 evidence 目录消耗唯一 reachability marker；失败即停止。
4. 创建唯一 parent checkpoint，再依次运行 baseline、treatment。两臂 message/environment/budget 必须同源，唯一 treatment exposure 为 repair packet。
5. Classified arm outcome 或 endpoint timeout 可继续另一臂；identity、evidence、budget、cleanup 或 unclassified failure 漂移立即停止。
6. 禁止 retry、replacement、backfill 和 schedule extension。

## 主要 outcome

主要 outcome 是 paired post-checkpoint P2 conversion，并要求 production candidate verification 与独立 clean replay 同时通过。请求数、recorded tokens、动作预算、R0 rejection 分布与墙钟仅作描述性指标。Artifact 正确但 P2 未证明仍记为失败。
