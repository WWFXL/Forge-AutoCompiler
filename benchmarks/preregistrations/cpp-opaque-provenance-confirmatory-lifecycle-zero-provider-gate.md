# Forge opaque provenance 六 case lifecycle 零 provider 门禁

- GitHub Issue：[Issue #232](https://github.com/WWFXL/Forge-AutoCompiler/issues/232)
- 状态：opt-in、零 provider、非正式实验
- 父协议：Issue #233 六 case confirmatory candidate v2 amendment
- Docker：仅允许 Ubuntu WSL2 原生 `docker.service`

## 目的

在实现 provider runner 或创建正式 checkpoint 前，验证六个 result-blind case 均能复用同一条生产 Compile Session 验收链。门禁只回答 case bootstrap、P2 构造、artifact oracle、clean replay 和 cleanup 是否在真实容器中可达，不估计模型效应。

## 最薄生命周期

每个 case 使用一个临时 Compile Session：

1. 在 `autocompiler:gcc13` 中检出冻结 exact commit，并确认 Dockerfile 已包含冻结系统依赖。
2. 执行一个 self-contained opaque wrapper，包含 bootstrap、冻结 target build 与 artifact stage。
3. 首次 submit 必须识别正确 artifact，但只因 `build_system_unproven` 拒绝；P2 reference 必须为 `unproven/opaque_wrapper`，且不启动 replay。
4. 在相同 append-only command history 上追加一次 direct CMake/Make build 和独立 stage；P2 必须转为 `proven/direct_cmake` 或 `proven/direct_make`。
5. 第二次 submit 必须通过 production artifact classification 与唯一 clean replay。
6. production finalize 必须在删除 compile container 后复核 accepted artifact，并以 `completed` 终结；本次创建的 compile/replay container 不得残留。

这不是正式 baseline/treatment pair，也不创建 checkpoint。单 Session 的目的只是验证共同生命周期接线，不能进入确认性效应估计。

## 冻结边界

- Case identity、bootstrap、configure 参数、target 和 artifact oracle 直接读取并严格校验 #233 candidate v2 manifest；#230 v1 保持不变。
- Compile image 固定为 `autocompiler:gcc13`，并固定 `docker/compile/Dockerfile` 的文件 SHA-256。
- CMake 使用 `Ninja` 与 `/workspace/repo/build`；Make 使用冻结 target；两者 direct build 均固定有界 `-j2`。
- Parent wrapper 只能在顶层暴露 `sh`，treatment 必须由可信 runtime 记录 direct build executable。
- 直接复用生产 `submit_build_result_impl`、clean replay 和 `cleanup_and_finalize_compile_session_impl`，不修改生产 Compiler 或 evaluator。

## 授权与停止规则

本门禁授权六个 opt-in Docker case，但固定 0 provider、0 credential read、0 checkpoint、0 formal attempt、0 model token 与 0 正式 evidence write。临时 session、ledger、replay 目录只存在于 pytest 临时目录并在结束时清理。

如果六个 case 无法共享同一 adapter，必须复制历史 checkpoint orchestration，或必须修改生产 Compiler 才能通过，则停止实现并重新评审；不得以 provider 调用、正式 evidence 或放宽 oracle 绕过失败。
