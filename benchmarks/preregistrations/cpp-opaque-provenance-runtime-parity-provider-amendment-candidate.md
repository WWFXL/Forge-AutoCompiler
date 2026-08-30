# Opaque build provenance runtime-parity provider amendment 候选

本候选承接 Issue #184 的冻结 canary 终态与 Issue #186 的零 provider runtime-parity 门禁。#184 treatment 在 repair build 之前被 measurement policy 机械阻止，属于 `measurement_policy_censored / intervention_delivery_failure`，不能作为 repair packet 或模型失败证据。#186 已证明真实 compiler-facing tool surface 在分项预算下可完成 direct build、automatic submit、candidate verification、clean replay 与 cleanup，但没有调用模型。

## 候选身份

- 父 execution manifest canonical SHA-256：`bbb50851419ec8c1e1efb4bc5612cb13e4ab0154df574dc7359009e2fb90529a`。
- 授权基线：`main@ad6e7c1143d23eeca0cd8f98dcb76023e6b81626`。
- 新 pair：`opaque-provenance-cppitertools-runtime-parity-pair-01`，顺序固定为 `baseline -> treatment`。
- Provider 候选保持 DeepSeek `deepseek-v4-flash`、`https://api.deepseek.com`、300 秒、0 retry、非 streaming、禁止 fallback。
- 新 evidence directory 与 #184 冻结目录分离；#184 `reports/canary.json` SHA-256 必须保持 `e6ee3e2db68c191e7c4e278071ea14a32e6ef362d82194d07697b0ea24034da0`。

## Runtime-parity 合同

双臂从同一个 committed message、environment、budget checkpoint 派生，并共享相同 measurement policy。Parent 必须经真实 bound `submit_build_result` wrapper 形成唯一 `build_system_unproven`，capture 前 post-build fence 三字段必须释放。

Checkpoint 后预算按语义动作分离：inspection 4、repair build 2、artifact stage 2、continuation submit 2。Repair build 只能使用冻结 `/workspace/repo/build` 与 target `accumulate_examples`；stage 只能把冻结 output 复制到冻结 `/artifacts` 路径。Clone、configure、dependency、housekeeping、manual replay、compound build+stage、越界 build directory/target 与超额动作继续 fail closed。预算 admission 与 consume 必须原子完成；provider tool binding 固定 `parallel_tool_calls=False`。

两臂唯一 treatment exposure 仍是既有白名单 repair packet。Runtime-parity policy 不是 treatment，因为 baseline 与 treatment 都使用它。该设计是新的 measurement-policy amendment，不是 #184 的 retry、replacement、backfill 或追加槽，结果不得与 #184 池化。

## 一次性机会与预算

未来 amendment 若另行授权，只允许一次 reachability 和一个新 pair。Reachability 最多 5,000 recorded tokens；每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间、120 秒 cleanup reserve与 120,000 recorded tokens；pair 上限 240,000，阶段机械上限 245,000。Reachability 失败时 pair 必须拒绝；identity、evidence、budget、cleanup 或未分类失败立即停止。禁止 retry、replacement、backfill 和 schedule extension。

## 当前授权边界

Issue #188 只授权生成、校验、计划与只读 preflight。Reachability、provider call、formal attempt、canary collection、credential 读取和 model creation 均未授权，execute path 必须机械拒绝。本阶段固定 0 provider、0 formal attempt、0 model token、0 evidence write，不修改 production Compiler、Oracle、`operations.py`、历史 manifest/runner 或 #184 evidence。

后续单 pair 即使成功，也只能判断 intervention delivery 与 post-checkpoint provenance conversion 是否可观察；不得估计 treatment effect、计算 p 值、排名模型或与其他 fault family 池化。
