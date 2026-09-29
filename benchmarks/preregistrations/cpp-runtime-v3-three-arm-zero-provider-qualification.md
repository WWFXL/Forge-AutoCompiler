# Runtime v3 三臂 state-matched 零 Provider qualification

日期：2026-09-29
状态：基础设施 qualification 已通过
Tracking Issue：#352

## 目的

本门禁验证 Runtime v3 candidate submission boundary 能否为后续契约驱动修复实验提供两个 fault strata、
三个反馈条件的同源 continuation。它只回答实验基础设施是否可执行，不产生反馈效果观测。

覆盖：

- `delivery_target`：生产 `CandidateVerifier` 产生 `target_mapping_invalid`；
- `provenance`：生产 candidate submission 加 P2 reference criterion 产生
  `build_system_unproven / opaque_wrapper`；
- C0：只暴露普通 `verification_failed`；
- T1：暴露 stratum 与 `code/paths/expected/actual` finding；
- T2：在 T1 上增加不含命令、补丁或答案的抽象 repair goal。

三臂共享 source、commit、continuation image、workspace、artifacts、parent command history、candidate
request、authoritative rejection、message prefix、remaining budget、tool/action policy、CandidateVerifier、
P2、functional oracle、external evaluator、clean replay 和 cleanup authority。`parallel_tool_calls=false`。

## 实现边界

- `scripts/forge_runtime_v3_three_arm_qualification.py` 是独立版本化 adapter；不导入或修补冻结 opaque
  replication runner。
- adapter 直接使用 Runtime v3 `AgentWorkflowCandidateService`。P2 只在生产 runtime 已给出唯一粗粒度
  `build_system_mismatch` 时接管；接管后仍先运行生产 CandidateVerifier，再执行 P2 reference criterion。
- feedback projection 使用精确字段集合；拒绝跨 pair/stratum evidence、非白名单字段、具体命令、argv、
  shell、patch、答案、credential 与 evaluator 信息。
- checkpoint 在 authoritative rejection 返回后、任何 continuation 或模型请求前创建；环境捕获期间暂停
  parent container，提交 rootfs，并复制 workspace/artifacts。C0/T1/T2 使用 opaque session identity 从该
  唯一 snapshot 派生。
- provenance continuation 通过真实 `run_container_bash` 工具面追加 direct-CMake build 与 artifact
  stage，禁止直接写 command record 伪造修复。
- external evaluator 使用 opaque evaluation identity，输入不含 arm label。

adapter 的 `validate` 命令动态记录 qualification adapter、Docker gate、Runtime v3、CandidateVerifier、P2、
external evaluator v3、compile operations 和 compiler tool surface 的当前 SHA-256；任一组件变化都会改变
authority identity。

## 实际执行结果

执行环境通过 `scripts/require-docker-runtime.sh`；使用本地固定提交的最小 CMake/Ninja 仓库和
`autocompiler:gcc13`，不依赖外部源码状态。

```bash
cd backend
FORGE_RUN_RUNTIME_V3_QUALIFICATION_DOCKER=1 \
  PYTHONPATH=. uv run pytest \
  tests/test_forge_runtime_v3_three_arm_qualification_docker.py -vv -s
```

最终复跑结果：`2 passed in 75.93s`。

| stratum | parent rejection | C0 | T1 | T2 |
| --- | --- | --- | --- | --- |
| delivery/target | production `target_mapping_invalid` | strict closed | strict closed | strict closed |
| provenance | P2 `build_system_unproven / opaque_wrapper` | strict closed | strict closed | strict closed |

每个 arm 的 `strict closed` 均表示 candidate accepted、functional oracle passed、provenance passed、external
evaluator v3 strict success、clean replay passed、finalize/cleanup passed。六个 arm 的合成计数均为
`model_requests=0`、`recorded_tokens=0`；阶段固定
`provider_calls=0`、`formal_attempts=0`、`experiment_evidence_writes=0`。运行前后 managed container、
paused container 和 managed image 均为 0。

非 Docker 门禁覆盖错误 packet、具体命令泄露、跨 pair evidence、state drift、budget drift、evaluator arm
label 泄露、orphan、checkpoint 重用和 manifest hash 漂移，共 `14 passed`。CandidateVerifier、P2 gate、
external evaluator v3 与 lifecycle checkpoint 相邻回归共 `77 passed`；定向 Ruff check/format 和
`git diff --check` 通过。

## 解释边界

本结果支持：Runtime v3 当前实现可以在两个候选 fault strata 上形成 state-matched C0/T1/T2，并以确定性
continuation 闭合严格工程终点。

本结果不支持：C0/T1/T2 存在 treatment effect、任一反馈条件更优、36 arms 具有足够功效、Provider 或模型
排名、自然失败总体外推。这里的六个 arm 是 qualification 执行，不得进入未来正式实验 outcome。

## 下一决策

研究负责人仍需在不读取新 outcome 的条件下冻结最小有意义效应、具体项目/checkpoint、独立性、执行顺序、
随机化、多重比较规则、Provider、预算、retry 与停止规则。完成这些决策后才能建立新的候选 manifest、Schema、
preregistration 和 plan-only runner；任何 Provider、credential、formal attempt 或 formal evidence 写入仍需独立
授权。
