# Forge opaque provenance 六 case 确认性 pilot 候选协议

- GitHub Issue：[Issue #230](https://github.com/WWFXL/Forge-AutoCompiler/issues/230)
- 状态：未授权、零 provider、零 Docker的静态候选
- 语言范围：C/C++
- 构建系统：CMake 与 Make

## 研究动机

现有 `cppitertools`、`yyjson` 与 `OpenH264` 三个有效 pair 只构成方向一致的探索性证据。协议在这些 case 之间持续演化、每个 case 只有一次模型 realization，且历史 arm order 固定为 baseline-first，因此不能池化为总体效应。

本候选在查看任何新 case 模型结果前，冻结六个全新 project block。每个 project 有两个独立 physical attempt/checkpoint replicate；一个 pair 为 `baseline -> treatment`，另一个为 `treatment -> baseline`。批次启动后不允许修改 packet、action validator、P2/R0、artifact oracle 或 schedule。

## 冻结来源

| 路径 | SHA-256 |
| --- | --- |
| `benchmarks/preregistrations/cpp-formal-v1-cases.json` | `55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee` |
| `benchmarks/preregistrations/cpp-formal-v1.json` | `3b7f1134637385f7236ea344c8b9816c04bc837143cb7ac4f8af1e007e7f08dc` |
| `benchmarks/manifests/cpp-formal-v1.json` | `cb9ad04c3d5452ab6ae3e12d1ef8658b8cf52876c6aecc3b251b2dd930e6944a` |

候选审计只读取冻结协议、本地历史 result evidence 的 `case_id` 和 GitHub exact-commit 源码。未运行构建、Docker 或模型。

## 六个 project block

| Case | Build | Direct target | Artifact |
| --- | --- | --- | --- |
| `pupnp@4c4285d6` | CMake | `upnp_static` | `build/upnp/libupnp.a`，static library |
| `ada-url@30f3f302` | CMake | `ada` | `build/src/libada.a`，static library |
| `args@fe4450bd` | CMake | `gitlike` | `build/gitlike`，executable；`--help` 返回 0 |
| `gpac@2aa431ea` | Make | `lib` | `bin/gcc/libgpac_static.a`，static library |
| `fio@c76c61b0` | Make | `fio` | `fio`，executable；`--help` 返回 0 |
| `sql-parser-shared@ccd3f68b` | Make | `library` | `libsqlparser.so`，shared library |

`sql-parser-shared` 是独立的新 identity。旧 formal source protocol 把默认 `make library` 的 artifact 写成 `libsqlparser.a`，但 exact-commit Makefile 定义 `static ?= no`，默认实际生成 `libsqlparser.so`。旧协议保持逐字不变；本候选只在新 identity 中修正 oracle，并以负例测试拒绝旧 static identity。

## 排除项

- `mruby`：`make all` 委派给 Rake，并会隐式初始化 Prism submodule；外部网络和二级构建工具混入 fault。
- `janet`：本地已有 formal v3 与 multi-checkpoint 模型结果，不再 result-blind。
- `lodepng`：`unittest` 捕获任意测试异常后仍返回 0，Forge 固定 smoke 无法区分测试成功与失败。
- `sql-parser-static`：旧 static artifact 与默认 direct target 输出不一致。

## 冻结 schedule

第一轮按 `pupnp, ada-url, args, gpac, fio, sql-parser-shared`；第二轮逆序。第一轮三个 baseline-first、三个 treatment-first；每个项目第二轮使用相反顺序。总计 12 pairs / 24 arms，pair 与 replicate 不得 replacement 或 backfill。

## Runtime 与测量合同

- 批次只使用一个预先冻结的 provider/model；具体 identity 必须在独立 execution amendment 中、首个请求前冻结。
- 每请求 timeout 300 秒、0 retry、禁止 fallback、禁止 parallel tool calls。
- 每 arm action limits 为 inspection/build/stage/submit `4/2/2/2`；最多 8 requests、8 turns、24 graph steps、600 秒 work 和 120 秒 cleanup。
- 每 arm recorded-token ceiling 120,000；24 arms 加独立 reachability 预留后的机械批次上限为 2,940,000。
- 双臂共享 tool contract，repair packet 是唯一 treatment exposure。
- Parent 必须只形成 `unproven/opaque_wrapper`；treatment 只有受信任 direct CMake/Make invocation 才能转为 proven。
- R0 companion、candidate verification、clean replay、cleanup 与 0 orphan 都是有效 measurement 的必要条件。

## Analysis

每个 replicate 的 paired conversion difference 为 `treatment - baseline`。每个 project score 是两个 replicate difference 的平均值，六个 project block 是独立分析单位。只有六个 project block 均可估计时才运行双侧 exact sign-flip；否则 primary test 标记为不可估计，并单独报告 endpoint censoring、mechanism invalid 与 intervention-delivery invalid。历史探索 pair 不进入新检验，不计算跨 provider 排名。

## 当前授权边界

本 Issue 只允许生成和验证 candidate manifest/schema。Provider、credential、model creation、reachability、checkpoint、pair collection、formal attempt、Docker、evidence write 与 model token 全部为 0/false；执行 runner 尚未实现，任何真实 lifecycle 或模型采集都需要新的版本化 amendment。
