# Stage C v6 四条候选失败审计

日期：2026-09-27。追踪：Issue #337。来源是 Stage C v6 唯一零 Provider 离线重评；authorized manifest canonical SHA-256 为 `00530ddc740ae98f0327a89e5a1860e9a983c9e47b9aaeabd27543f4c75f23dd`，正式执行 release 为 `13928727bae286eb96a0c96173f63a513236259a`。

## 审计边界

本审计只读回溯 v6 的 4 条 strict failure，不修改、重跑、替换或回填 v5/v6 evidence。审计期间 0 formal attempt、0 Provider request、0 input/output/total token。v5 的 A `19/24`、B `0/24` 与 v6 的 `18/22` 都保持原结论。

输入身份包括：v6 聚合结果 SHA-256 `be0783c1...f42f`、来源收据 SHA-256 `098c6fef...c25`、正式 inventory SHA-256 `90b479a1...ce36` 和 batch-completed marker SHA-256 `47c1745b...cab07`。每条 candidate、来源 Session 和 v6 result 的完整哈希见机器可读报告。

## 审计结论

4 条候选的冻结 recipe 命令证据均通过 S1，因此没有“构建命令未成功”的证据。3 条功能 oracle 通过；`json-c r2` 的 oracle 因 `json.h` 引用但未交付 `arraylist.h` 而失败。`theora r1`、`json-c r2`、`oatpp r2` 的 clean replay 都执行成功且 bitwise reproducible，说明失败交付能够稳定重现；`libjpeg-turbo r2` 在候选验证阶段失败，未生成 replay recipe。

| Case | 直接失败 | 冻结证据 | 审计分类 |
| --- | --- | --- | --- |
| `theora r1` | 未声明 `libtheoradec.a`、`libtheoraenc.a`，并交付 0-byte `doxygen-build.stamp` | oracle 通过；18 文件 bitwise replay | 可复现的无效 delivery |
| `json-c r2` | 多出 `json-c-public-headers` target；只交付 `json.h`，公共头文件闭包不完整 | replay bitwise；oracle 编译报缺少 `arraylist.h` | 无效 target + 不完整 header closure |
| `libjpeg-turbo r2` | broad install 交付未声明 `libturbojpeg.a` 和工具；3 个额外工具默认 smoke 失败 | 静态库 oracle 通过；无 replay recipe | candidate verifier 阻断的 broad delivery |
| `oatpp r2` | `OATPP_LINK_TEST_LIBRARY=ON` 交付未声明 `liboatpp-test.a` | oracle 与 184 文件 bitwise replay 均通过 | 可复现的无效 delivery |

这些结果符合 external evaluator v4 的冻结三集合语义：delivery manifest 可以包含未逐项声明的 support files，但不能包含未声明的 executable、library 或 object；所有文件必须有效且非空；`target_mapping` 必须只绑定冻结的唯一 target ID。因此 evaluator defect、远程 Git、runner 异常和 cleanup 均不是这 4 条的根因。

## 共同机制缺口

`AgentWorkflowCandidateService._validate_against_session()` 只遍历 candidate 声明的 `artifact_paths`，检查这些路径是否存在、是否为常规文件和是否为符号链接。Runtime v2 只再检查 `required_candidate_artifacts` 是否被声明。它们没有在 candidate create-once 冻结前：

- 扫描并分类完整 `/artifacts` delivery；
- 拒绝未声明 compiled artifact 或 0-byte 文件；
- 把 `target_mapping` key 与 node input 的唯一 target ID 对齐；
- 运行受信功能检查以发现 header closure 缺失。

external evaluator 会独立执行这些判定，但此时 candidate 已冻结，Agent 无法在同一 attempt 内修复。4 条都是有效的候选/方法失败，同时共同暴露了“验证反馈发生得过晚”的运行时机制缺口；不能据此把它们追认为成功。

## 下一阶段决策

暂不启动新的配对校准，也不修改 evaluator v4。下一阶段先实现零 Provider 的 pre-freeze candidate verifier 门禁：

1. candidate 持久化前扫描完整 delivery，并复算文件类型、大小和路径集合。
2. 对唯一 target ID、未声明 compiled artifacts、无效或零字节文件返回有界结构化拒绝证据，让 Agent 能在原 attempt 预算内修复 staging。
3. 增加受信的冻结前功能检查接口，覆盖 `json-c` 这类 header closure；正式 external evaluator 仍在冻结后独立重算并保持最终权威。
4. 用这 4 类失败构造只读 fixture，先通过单元与真实 Docker lifecycle 门禁，再发布新 runtime/experiment identity。

只有上述门禁通过后，才讨论新的 Provider canary 或独立实验。机器可读细节见 `benchmarks/reports/cpp-stage-c-v6-failure-audit.json`。
