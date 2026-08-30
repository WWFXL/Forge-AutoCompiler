# R3 Make 单配对 execution amendment

- Issue：[#218](https://github.com/WWFXL/Forge-AutoCompiler/issues/218)
- 父 candidate：#216 / PR #217，canonical SHA-256 `e45c9a5cfbba70d30ee2c82a68631a3430ea3e66748d808888660cae5c105d7b`。
- 网络：Wi-Fi；Ubuntu WSL2 原生 Docker Engine；Compose/DooD control plane。

## 冻结执行

DeepSeek `deepseek-v4-flash`、`https://api.deepseek.com`、300 秒、0 retry、禁止 fallback、非 streaming。只允许一次 reachability；通过后只允许一个 `baseline -> treatment` state-matched pair。每臂最多 8 requests / 8 turns / 24 graph steps / 120,000 recorded tokens，阶段上限 245,000。Marker 在开始时消耗，禁止 retry、replacement、backfill 和 extension。

双臂共享 direct Make、目录、target、jobs 省略或 `1..2`、独立 stage 与 R0 companion 合同；repair packet 是唯一 treatment exposure。底层 P2 reference case ID 与 R3 experiment case ID 分开记录。

## 停止与解释

Reachability、identity、预算、evidence、cleanup、unclassified failure 或 orphan gate 任一失败立即停止。Endpoint timeout 记录为删失，不解释为编译能力。结果只做单 pair 描述，不与 #208 或两个 CMake pair 池化，不计算 p 值，不排名模型。
