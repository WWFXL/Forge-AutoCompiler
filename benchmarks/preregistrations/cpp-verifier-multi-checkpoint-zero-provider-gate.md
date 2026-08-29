# 跨构建系统多 checkpoint 零 provider 门禁

## 研究目的

behavioral pilot v2 的 6 个配对全部来自同一个 `cppitertools` CMake checkpoint。本门禁只验证 `artifact_staging_missing` controlled fault 能否在 CMake、Make、Autotools 三种构建系统和三个独立项目上形成相同的可恢复 checkpoint，不产生 repair effect 结论。

## 冻结 case

| Case | 角色 | 构建系统 | 唯一 required artifact |
| --- | --- | --- | --- |
| `cppitertools@531b3d7` | 已验证 anchor | CMake | `.forge-cmake-build/accumulate_examples -> accumulate_examples` |
| `janet@c0b32d4` | 新 gate | Make | `build/libjanet.a -> libjanet.a` |
| `libcheck@11970a7` | 新 gate | Autotools | `src/.libs/libcheck.a -> libcheck.a` |

`hiredis` 因要求两个产物而排除；历史 `openthread`/`mupdf` fixture 不含真实可恢复环境，也不进入本门禁。

## 执行契约

1. 严格校验 repo、exact commit、build system、依赖、命令顺序、单产物路径和历史 protocol artifact hash。
2. 对每个新 case 执行真实 parent build，将唯一产物暂存到 `/artifacts`，再由 controlled fault v1 只删除 staged artifact。
3. 真实 candidate verifier 必须产生唯一 pre-replay `candidate_verification_failed`，且 `replay_attempts == 0`。
4. 从同一个 committed message/environment/budget checkpoint 派生 baseline/treatment；两臂初始环境同源且写入隔离。
5. 两臂只执行确定性 artifact restore，随后 candidate verification 与 clean replay 都必须通过。
6. cleanup 后 0 paused/orphan container、continuation image、helper 和 snapshot。

## 环境与授权

- Docker 只使用 WSL Ubuntu 原生 `docker.service` 与 Forge Compose/DooD 共享 daemon，不使用 Docker Desktop。
- Provider calls、formal physical attempts 和 model tokens 均为 0；不读取任何 AK。
- 不修改 production Compiler、Oracle、clean replay、自然任务 ITT、primary canary、behavioral v2 runner 或冻结 evidence。
- 本 gate 通过不授权 3 cases x 2 pairs、第二 provider 或 natural-failure collection。

## 停止规则

任一 case 的 exact commit、构建、fault classification、checkpoint identity、candidate/clean replay 或 cleanup 失败即停止并保留诊断；不得切换 Docker daemon、调用 provider 或把失败回填到 behavioral v2。
