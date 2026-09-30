# 契约驱动修复 mechanism v2 独立 36-arm candidate

## 决策与性质

研究负责人选择从零建立全新的 36-arm identity。该选择不续跑、不修补、不导入也不回填 mechanism v1 formal failure identity。旧 identity 的 sequence 1 T2 arm 永久排除于 v2 的主要、次级和支持性分析，只作为 runner marker 合同失败的基础设施证据保留。

本 candidate 属于工程修复与实验基础设施阶段。它冻结未来独立采集的身份和门禁，不读取 credential、不调用 Provider、不创建 Docker Compile Session、不创建 formal attempt，也不写 formal experiment evidence。`qualify` 仅在自动删除的临时目录中检查 marker repair，不构成实验 observation。

## 继承的科学合同

v2 原样继承 mechanism v1 已冻结的下列内容：

- 6 个项目、每项目 delivery/target 与 provenance 两个 checkpoint，共 12 checkpoints；
- 每 checkpoint 的 C0/T1/T2 三臂条件和固定执行顺序，共 36 arms；
- 主要比较 C0 vs T1，次级比较 T1 vs T2，支持性比较 C0 vs T2；
- DeepSeek `deepseek-flash`、300 秒请求超时、SDK retry 为 0、`parallel_tool_calls=false`；
- 每 arm 最多 8 个 Provider request attempts，36 arms 的机械上限为 288；
- recorded tokens 逐请求记录且不设 ceiling，token 总量不作为停止条件；
- 前四个 formal arms 中出现两个 endpoint-censored arms 时停止整个 identity；
- identity、checkpoint、ledger、预算、evaluator、cleanup 或 orphan 异常立即停止；
- project-level exact sign-flip、多重比较 gate、最小有意义效应和缺失数据报告规则。

新 identity 不根据已经观察到的 v1 首 arm 改变任务、condition 顺序、预算、停止规则或分析规则。36 arms 仍是固定样本机制研究，不是总体功效充分的确认性实验。

## 独立身份

- 使用新的 deterministic opaque-ID seed，生成 36 个 clone IDs 和 36 个 evaluation IDs；两组 ID 均与 v1 零重叠。
- 使用新的 create-once evidence root：`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent`。
- v1 的 availability marker、checkpoint、arm marker、ledger、result、token 和 outcome 均不导入。
- 未来执行前必须在 v2 evidence root 内完成独立 availability execution；历史 availability 不复用。
- v1 的 9 文件、66,466 bytes 和 inventory SHA-256 `24019a372a3b49fe6dc1b141da45f09f764639c253fc1ed16521341f3c6d2fb5` 保持只读。

## Marker repair

v2 显式绑定 `scripts/forge_contract_driven_repair_mechanism_v1_formal_marker_repair.py`，其文件 SHA-256 为 `07e781c220a3f315f823a127bb1a0f839dfa81ceca99d2266f6fa10be97c073c`。Repair 绑定 frozen v1 runner SHA-256 `5bb1797d2a3a5a8c700ba8da5677b195d0c0db969498521df878f669c815e358`，只在新 identity 的串行进程绑定中把 keyword updates 转换为旧 helper 所需的 mapping。

零 Provider qualification 必须覆盖并持久化：

1. attempt marker 终态；
2. batch progress；
3. batch 正常终态；
4. batch 异常终态。

冻结 v1 runner 不修改，旧 marker 不修补。

## Candidate 权限边界

允许的命令仅为 `validate`、`plan`、`qualify` 和 `preflight`。`availability`、`batch`、`report` 与 `audit` 在 candidate runner 中 fail-closed。

非模型 preflight 只检查：clean `main == origin/main`、基线后代关系、Docker runtime 与冻结 image ID、零 managed resources、旧 evidence inventory 未漂移，以及新 evidence root 不存在。它不得读取 credential 或创建 evidence、marker、容器、attempt、模型和 token。

合并本 candidate 不构成真实执行授权。未来 execution identity 必须绑定合并后的 exact release、新 availability identity、credential/Provider/model/evidence 权限和相同停止规则；在该 identity 合并并获得研究负责人明确授权前，不得启动任何 v2 Provider request。

## 解释边界

本阶段只能支持独立身份、旧证据排除、marker repair 和非模型门禁已经机械闭合。它不能支持 C0/T1、T1/T2、C0/T2 treatment effect，不能产生 p 值、总体成功率、Provider/model 排名或跨项目外推。
