# Jev 未见项目族正式三臂比较 v1

- Tracking Issue：[#408](https://github.com/WWFXL/Forge-AutoCompiler/issues/408)
- Identity：`cpp-jev-formal-comparison-v1`
- Implementation revision：`7dda64349f774dfe02e69234f6b3eadf0120e256`
- Manifest canonical SHA-256：`b9be8ff7568934ef13c00b5cb7fc8a9810fe43dfb487e7edc1a63c48f45d5a4d`

## 研究问题

在 12 个未参与 Jev 资格、校准或 canary 的项目族上，`JevGate+Agent` 能否相对
`AlwaysAgent` 保持严格成功率非劣并降低 Provider 成本？`RuleGate+Agent` 作为冻结的简单规则基线。

样本覆盖 CMake、Make、Autotools 各四个项目，exact commit 均晚于
`2026-10-08T20:06:00Z`。每个项目、每个 arm 独立运行两次，共 72 arms。
故障均为受控故障，结论不得外推到自然失败分布。

## 样本

- `libgit2` / `cmake` / `invalid_build_state` / 预期 `configure`
- `simdjson` / `cmake` / `wrong_build_target` / 预期 `build`
- `benchmark` / `cmake` / `missing_compile_input` / 预期 `dependency`
- `pcre2` / `cmake` / `invalid_build_state` / 预期 `configure`
- `haproxy` / `make` / `wrong_build_target` / 预期 `build`
- `cc65` / `make` / `missing_compile_input` / 预期 `dependency`
- `ffmpeg` / `make` / `invalid_build_state` / 预期 `configure`
- `redis` / `make` / `wrong_build_target` / 预期 `build`
- `libarchive` / `autotools` / `missing_compile_input` / 预期 `dependency`
- `curl` / `autotools` / `invalid_build_state` / 预期 `configure`
- `jemalloc` / `autotools` / `wrong_build_target` / 预期 `build`
- `wolfssl` / `autotools` / `missing_compile_input` / 预期 `dependency`

## 固定顺序

1. repetition `1` / `libgit2` / `always_agent`
2. repetition `1` / `libgit2` / `rule_gate_agent`
3. repetition `1` / `libgit2` / `jev_gate_agent`
4. repetition `1` / `simdjson` / `rule_gate_agent`
5. repetition `1` / `simdjson` / `jev_gate_agent`
6. repetition `1` / `simdjson` / `always_agent`
7. repetition `1` / `benchmark` / `jev_gate_agent`
8. repetition `1` / `benchmark` / `always_agent`
9. repetition `1` / `benchmark` / `rule_gate_agent`
10. repetition `1` / `pcre2` / `always_agent`
11. repetition `1` / `pcre2` / `rule_gate_agent`
12. repetition `1` / `pcre2` / `jev_gate_agent`
13. repetition `1` / `haproxy` / `rule_gate_agent`
14. repetition `1` / `haproxy` / `jev_gate_agent`
15. repetition `1` / `haproxy` / `always_agent`
16. repetition `1` / `cc65` / `jev_gate_agent`
17. repetition `1` / `cc65` / `always_agent`
18. repetition `1` / `cc65` / `rule_gate_agent`
19. repetition `1` / `ffmpeg` / `always_agent`
20. repetition `1` / `ffmpeg` / `rule_gate_agent`
21. repetition `1` / `ffmpeg` / `jev_gate_agent`
22. repetition `1` / `redis` / `rule_gate_agent`
23. repetition `1` / `redis` / `jev_gate_agent`
24. repetition `1` / `redis` / `always_agent`
25. repetition `1` / `libarchive` / `jev_gate_agent`
26. repetition `1` / `libarchive` / `always_agent`
27. repetition `1` / `libarchive` / `rule_gate_agent`
28. repetition `1` / `curl` / `always_agent`
29. repetition `1` / `curl` / `rule_gate_agent`
30. repetition `1` / `curl` / `jev_gate_agent`
31. repetition `1` / `jemalloc` / `rule_gate_agent`
32. repetition `1` / `jemalloc` / `jev_gate_agent`
33. repetition `1` / `jemalloc` / `always_agent`
34. repetition `1` / `wolfssl` / `jev_gate_agent`
35. repetition `1` / `wolfssl` / `always_agent`
36. repetition `1` / `wolfssl` / `rule_gate_agent`
37. repetition `2` / `libgit2` / `rule_gate_agent`
38. repetition `2` / `libgit2` / `jev_gate_agent`
39. repetition `2` / `libgit2` / `always_agent`
40. repetition `2` / `simdjson` / `jev_gate_agent`
41. repetition `2` / `simdjson` / `always_agent`
42. repetition `2` / `simdjson` / `rule_gate_agent`
43. repetition `2` / `benchmark` / `always_agent`
44. repetition `2` / `benchmark` / `rule_gate_agent`
45. repetition `2` / `benchmark` / `jev_gate_agent`
46. repetition `2` / `pcre2` / `rule_gate_agent`
47. repetition `2` / `pcre2` / `jev_gate_agent`
48. repetition `2` / `pcre2` / `always_agent`
49. repetition `2` / `haproxy` / `jev_gate_agent`
50. repetition `2` / `haproxy` / `always_agent`
51. repetition `2` / `haproxy` / `rule_gate_agent`
52. repetition `2` / `cc65` / `always_agent`
53. repetition `2` / `cc65` / `rule_gate_agent`
54. repetition `2` / `cc65` / `jev_gate_agent`
55. repetition `2` / `ffmpeg` / `rule_gate_agent`
56. repetition `2` / `ffmpeg` / `jev_gate_agent`
57. repetition `2` / `ffmpeg` / `always_agent`
58. repetition `2` / `redis` / `jev_gate_agent`
59. repetition `2` / `redis` / `always_agent`
60. repetition `2` / `redis` / `rule_gate_agent`
61. repetition `2` / `libarchive` / `always_agent`
62. repetition `2` / `libarchive` / `rule_gate_agent`
63. repetition `2` / `libarchive` / `jev_gate_agent`
64. repetition `2` / `curl` / `rule_gate_agent`
65. repetition `2` / `curl` / `jev_gate_agent`
66. repetition `2` / `curl` / `always_agent`
67. repetition `2` / `jemalloc` / `jev_gate_agent`
68. repetition `2` / `jemalloc` / `always_agent`
69. repetition `2` / `jemalloc` / `rule_gate_agent`
70. repetition `2` / `wolfssl` / `always_agent`
71. repetition `2` / `wolfssl` / `rule_gate_agent`
72. repetition `2` / `wolfssl` / `jev_gate_agent`

## 三臂

- `always_agent`：故障状态直接升级完整 Agent。
- `rule_gate_agent`：固定选择 `build`；动作失败时升级完整 Agent，动作成功时由确定性 continuation 和同一 evaluator 收口。
- `jev_gate_agent`：Jev 以正序/逆序 Choice 判断动作，经冻结 Platt 门禁后直接执行或升级 Agent；动作失败时升级完整 Agent。

直接动作只执行代码绑定命令，不能生成 Shell，也不能宣告成功。所有候选必须经过 CandidateVerifier、functional oracle、provenance 和 clean replay。

## 固定预算

- 每 arm Agent：最多 24 请求、300000 tokens、1800 秒；
- 全阶段 Agent：最多 1728 请求、21600000 tokens；
- Jev：最多 24 请求、480000 input tokens、`$0.02016`；
- Provider retry 均为 0；不存在 replacement 或 backfill。

## 主要判据与统计

- 项目族聚类 bootstrap：seed `40820261011`，重复 `20000` 次；
- Jev 相对 AlwaysAgent 的 strict success 差值单侧 95% 下界不低于 `-10%`；
- Jev 相对 AlwaysAgent 的总 Provider 成本至少下降 `20%`；
- 两项必须同时成立，才支持正向主结论；同时报告分构建系统结果、RMST、请求、tokens、升级率和错误直接动作率。

## 停止规则

identity/evidence 损坏、预算越界、cleanup/orphan 失败立即停止整个 batch。Provider、模型行为、
无候选、超时和严格验证失败均保留为 arm outcome；不 replacement、不 backfill、不依据正式结果改阈值。

## 解释边界

本实验只支持对受控构建失败、冻结模型和当前 12 个项目族总体的推断；不支持自然失败泛化、
通用模型排名或动态预算优越性。直接动作不能绕过 CandidateVerifier、functional oracle、provenance 或 clean replay。
