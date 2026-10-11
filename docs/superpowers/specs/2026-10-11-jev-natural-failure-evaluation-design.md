# Jev 混合链路自然构建失败评测设计

日期：2026-10-11。追踪：Issue #411。父工程证据：Issue #409 的
`cpp-jev-hybrid-workflow-canary-v1`。父方法证据：Issue #408 的
`cpp-jev-formal-comparison-v6`。

## 1. 研究问题与阶段定位

Issue #408 已在人工构造的缺失输入、失效构建状态和错误 target 上观察到
`JevGate+Agent` 的严格成功率与成本优势；Issue #409 已证明 Workflow、Jev、Agent、
严格 verifier 和 cleanup 可以形成真实 Provider 闭环。两项证据都没有回答自然发生的构建失败。

本阶段先回答一个必要的资格问题：

> 能否从公开、时间冻结且未进入 Forge 历史实验的 C/C++ 项目中，构造跨 CMake、Make、
> Autotools 的稳定自然失败 checkpoint，并为 `dependency`、`configure`、`build` 三类
> 代码绑定动作建立可重复的真实 outcome matrix？

只有数据资格通过，才允许派生 Provider 三臂实验，比较：

- `AlwaysAgent`；
- `RuleGate+Agent`，RuleGate 固定选择 `build`，候选不满足前置条件时升级 Agent；
- `JevGate+Agent`，使用冻结校准门禁选择直接动作或升级 Agent。

本阶段属于数据收集和 benchmark 资格审计。固定计数器只是安全预算，不构成动态预算控制证据。

## 2. 自然失败定义

一个项目只有同时满足以下条件，才进入自然失败 benchmark：

1. 从公开仓库的冻结 exact commit 创建全新源码和构建目录；
2. 使用冻结 Forge 镜像和该构建系统的标准初始路径，不删除源码、不损坏 build tree、不指定错误
   target、不注入错误环境变量；
3. 两个独立 clean session 均以非零退出结束，且失败阶段和规范化错误类别一致；
4. 失败不是 clone、submodule、基础镜像、Docker、磁盘、网络、超时或 harness 自身错误；
5. 独立审核的 reference recipe 能在两个新 clean session 中通过 target、functional oracle、
   provenance 和 clean replay；
6. 从冻结失败 checkpoint 执行候选动作时，至少一个直接动作可以继续到严格成功。

初始路径直接成功、两次失败不一致、只发生资源/基础设施失败、没有可审计 reference closure，或只有
放宽 verifier 才能成功的项目，均保留记录但不进入后续 Provider 分母。

## 3. 抽样框与结果盲选择

### 3.1 来源和排除

- 抽样框固定为 `seclab-fudan/CXXCrafter-Community-Edition` revision
  `bac70e99e48b210a350c18b3f93efd839787ce37` 的 `data/top100_dataset.csv`。
- CSV SHA-256 固定为
  `39b0a41198ae7d92713b2f2c75cf691bb75aba5da56068edee18606272384bf9`。
- 构建系统元数据固定为同 revision 的 `script/count_for_build_system_top100.txt`，SHA-256 为
  `5e4e986db6e21d13e38e9497462c8a6f26985fe53ce251ad8978dd218e9585a4`。
- 排除设计冻结时已出现在 `benchmarks/fixtures/*.json` 或
  `benchmarks/manifests/*.json` 的全部 canonical project family；不读取其历史 outcome 来选择新样本。
- 只接收公开 GitHub 仓库、未 archived、GitHub `size <= 300000 KiB` 的项目。该限制控制 clone 和
  clean replay 成本，不依据构建结果调整。

### 3.2 分层和排序

选择 seed 固定为 `forge-jev-natural-failure-source-v1-2026-10-11`。对每个剩余 project family：

1. 从冻结 CXXCrafter 元数据取得 `CMake`、`Make`、`Autotools` 能力集合；
2. 以 `sha256(seed + NUL + family + NUL + system)` 最小值分配唯一构建系统；
3. 在系统内以 `sha256(seed + NUL + family)` 升序排列；
4. 按该顺序取前 8 个满足仓库元数据门槛的项目；若某层不足 8 个，不从其他层补齐。

exact commit 在 `2026-10-11 06:03:27 UTC` 从远端 `HEAD` 解析并冻结。构建观察开始后不得替换、
回填或改用新 commit。

| 角色序号 | 构建系统 | 项目 | exact commit |
| --- | --- | --- | --- |
| 1 | CMake | `rui314/mold` | `c522789231c9de8afb35722bf8c859341f1fcef6` |
| 2 | CMake | `flameshot-org/flameshot` | `019bea68a4a2e4e0d311cce80eda0652c55b81df` |
| 3 | CMake | `openalpr/openalpr` | `736ab0e608cf9b20d92f36a873bb1152240daa98` |
| 4 | CMake | `treefrogframework/treefrog-framework` | `f54f60220aa4b10ed69d541a3a3547259fc695c4` |
| 5 | CMake | `apache/kvrocks` | `dc8bc3afdc31aa7aebab832dfcbaf2d850ec70e5` |
| 6 | CMake | `jarikomppa/soloud` | `e82fd32c1f62183922f08c14c814a02b58db1873` |
| 7 | CMake | `ossrs/srs` | `185f78597370767311a52e49bc72e5fae3fee79b` |
| 8 | CMake | `RPCS3/rpcs3` | `7b4de2f13dfe6da28129e2e5905dca79c87cfde8` |
| 1 | Make | `ipkn/crow` | `2b43d3cd6a9a9cdbc99dfef9b86ff3f3027f3d1f` |
| 2 | Make | `webmproject/libvpx` | `ed2a5b572f0f62a72d2e483dd3031841f08fb343` |
| 3 | Make | `SerenityOS/serenity` | `80baeb29708ae10f4a4cc8a07ca57e9876c3e3d8` |
| 4 | Make | `videolan/x265` | `419182243fb2e2dfbe91dfc45a51778cf704f849` |
| 5 | Make | `BVLC/caffe` | `9b891540183ddc834a02b2bd81b31afae71b2153` |
| 6 | Make | `hoffstadt/DearPyGui` | `df9dabfc74b13686000d0c95441d0fc862d6313d` |
| 7 | Make | `facebook/rocksdb` | `4b44c2b4ba9c08b269d9689c69177553f1200bad` |
| 8 | Make | `id-Software/DOOM` | `a77dfb96cb91780ca334d0d4cfd86957558007e0` |
| 1 | Autotools | `rethinkdb/rethinkdb` | `a2cf1308b57dca2e05d744f225a082881bab3fca` |
| 2 | Autotools | `dmlc/xgboost` | `73e9188ff2674e7197f3e7f0ac03c851975dd004` |
| 3 | Autotools | `twitter/vireo` | `7f0bc1ad50f5eaf30a09de209f0172f2def36abd` |
| 4 | Autotools | `tesseract-ocr/tesseract` | `b2544450ca01407259ed53c870b7e5e4c67f7789` |
| 5 | Autotools | `strukturag/libde265` | `4fb298ec1af0686211dc2def73f4f41c2ce19ce5` |
| 6 | Autotools | `geany/geany` | `956e5be9060df37abf5bd9039c8758709f2a6f8d` |

系统内序号 1--2 为 design，3--4 为 calibration，5--8 为 evaluation。项目不合格时保留空位，
角色不得前移；这避免依据失败类型选择更有利的 evaluation 样本。

## 4. 冻结环境和标准初始路径

- 镜像：`autocompiler:gcc13@sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`。
- clone 和 submodule 在 host 完成；进入构建前记录 source snapshot、submodule commit、tracked file
  count 和仓库状态。源码不满足 exact commit 或非 clean 时 fail closed。
- 初始构建禁用网络；并发度固定为 4；每条命令最多 300 秒，每个 session 最多 600 秒。
- 日志保存完整 stdout/stderr，同时生成去除路径、时间和并发噪声的规范化错误摘要。

标准路径为：

- CMake：`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`，成功后执行
  `cmake --build build --parallel 4`；
- Make：直接执行 `make -j4`；
- Autotools：优先执行仓库已有的 `./autogen.sh`，其次 `./bootstrap`，否则
  `autoreconf -fi`；随后执行 `./configure` 和 `make -j4`。

项目根缺少相应入口、入口不是普通文件，或 CXXCrafter 元数据与 exact commit 不一致时，记为
`source_contract_ineligible`，不得改选另一构建系统。

## 5. Reference recipe 与严格 oracle

初始双 replay 完成后，允许在 design/calibration/evaluation 全部候选上进行一次结果可见的数据整理，
但必须遵守统一审核表：

- recipe 的每个依赖包、配置参数、target、产物和 oracle 都必须能从仓库文档、构建文件或失败日志追溯；
- 不接受源码补丁、跳过编译、下载预构建目标产物、关闭 provenance，或把“命令退出 0”当成功；
- dependency 必须列出固定包名，并记录实际解析版本；配置和构建命令必须使用 argv/脚本白名单；
- target 至少绑定一个 ELF 可执行文件或库；functional oracle 必须执行目标功能或编译并运行消费者；
- clean replay 从全新源码和构建目录重复整个 recipe，且 target hash/类型、oracle、provenance 一致；
- 每份 recipe 由独立审计函数检查命令目录、路径边界和禁止项，再运行两个 clean session。

如果需要修改通用动作语义、初始路径或 verifier，必须关闭 v1；不得把修改后的运行续写到同一 identity。

## 6. Typed action 合同与 outcome matrix

从每个合格项目的冻结自然失败 checkpoint 派生三个隔离副本。动作只暴露 family，不向 Jev 泄漏
命令文本、包名或 reference 答案。

- `dependency`：只执行 recipe 中冻结的依赖安装动作，然后回到失败前的标准 Workflow；
- `configure`：清理生成的构建状态，只执行 recipe 中冻结的 bootstrap/configure 动作，然后回到
  标准 Workflow；
- `build`：不安装依赖、不修改配置，只执行冻结 build 动作，然后进入统一 verifier；
- `escalate_agent`：不作为离线直接动作执行，只在后续 controller 中调用完整 Agent。

每个动作分支最多 900 秒，无隐式重试。分支终态按相同 S0--S5、functional oracle、provenance 和
clean replay 判定为 `strict_success`、`bounded_failure` 或 `infrastructure_failure`。三动作矩阵在第二个
全新 checkpoint 上完整 replay；类别必须逐项一致，失败与部分结果都保留。

“安全动作”指该动作分支通过完整严格终点。多个动作可同时安全；旧 Agent 行为、reference recipe 中
动作顺序和文本相似度都不作为标签。

## 7. 零 Provider qualification 门槛

v1 通过必须同时满足：

1. 三个构建系统各至少有 1 个 design、1 个 calibration 和 2 个 evaluation 自然失败项目；
2. 所有入选项目的双初始 replay、双 reference closure 和双三动作 matrix 类别完全一致；
3. evaluation 样本的安全动作并集至少包含两种直接动作 family；
4. 固定 `build` RuleGate 的 top-1 安全率不高于 75%，确保存在可辨识的路由问题；
5. 所有严格成功均使用相同 verifier，无 cleanup failure，最终为 0 managed resources；
6. 0 credential read、0 Jev request、0 Agent Provider request、0 model token。

任一门槛失败即冻结负结果并停止 Provider 阶段，不替换项目、不调整角色、不修改动作合同。

## 8. 资格通过后的 Provider 设计

资格通过后另行冻结 Provider identity；以下是不得在看到 Provider 结果后更改的上层合同：

- design 项目只允许确定 prompt/schema；calibration 项目只允许拟合安全概率和选择阈值；
  evaluation 项目一次性分析；
- 三臂共享 exact checkpoint、Agent 模型与预算、候选动作、verifier、超时和运行顺序随机种子；
- evaluation 每项目每臂 2 次，失败、超时和 Provider 错误全部进入分母；
- 主要非劣界：`JevGate+Agent - AlwaysAgent` 严格成功率的项目族聚类单侧 95% bootstrap 下界
  不低于 `-0.10`；
- 同时要求 JevGate Provider 总费用至少下降 20%，Jev 直接动作错误率不超过 10%；
- 次要指标包括完整 Agent handoff、Jev/Agent 请求、token、费用、墙钟 RMST、动作数、升级率和
  S0--S5；不得只报告成功案例成本。

若 evaluation 数量不足以支撑聚类区间，后续只能定位为可行性研究，不能声称总体非劣。

## 9. 结论边界

qualification 通过只说明这 22 个固定候选中存在可重复、可严格验证且 RuleGate 未饱和的自然失败
子集，支持进入独立 Provider 评测；它不证明 Jev 有效。qualification 失败只说明当前抽样框、冻结镜像、
动作目录和资源上限不能形成预注册 benchmark，不等于所有自然构建失败都不可路由。

即使后续 Provider 比较通过，贡献也应表述为自动化编译领域的类型化语义路由、严格 benchmark 和
系统实证结果，而不是通用路由或置信度机制创新。
