# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：Issue #427 的 `cpp-dynamic-budget-trajectory-benchmark-qualification-v5` 唯一正式零 Provider attempt 已完整通过，
  决定为 `proceed_to_agent_continuation_qualification_design`。冻结的 CMake、Make、Autotools 各 3 个项目全部完成，
  共 9/9 项目、27/27 连续状态和 54/54 同源禁网 Docker continuation。
- 核心证据：54/54 continuation exit 0，27/27 successor 重复一致、checkpoint 绑定、六维预算守恒和动作后权威
  观察闭合，3/3 build-system block 的 stop reservation 转移通过。三个 block 分别记录 CMake `32,218 ms`、
  Make `18,082 ms`、Autotools `79,040 ms`，均消费冻结的 18 次执行且未超过 900,000 ms 上限；总 recorded action
  wall clock 为 `129,340 ms`。
- 完整性与运行边界：raw evidence audit 为 326 files / 19,191,933 bytes，inventory canonical SHA-256
  `b29d6738344771f2b1a31d4d874390342fadfe5d6cad79db0d6a6c83f40d35d1`；0 credential、0 Provider、0 Agent，
  cleanup 后 0 managed container。正式 run 在 raw result、marker 和 inventory 封口后因旧 reporter 对成功结果
  `failure: null` 调用 `.get` 而退出；v5 增加只读内存兼容层后 audit/report 通过，raw evidence 和 inventory 未修改，
  正式 attempt 未重跑。
- 解释与下一步：v5 证明跨三种构建系统的 checkpoint 恢复、重复 continuation、动作后观察和共享预算计量基础合格，
  不证明动态预算 controller、Jev 或 Agent continuation 有效果。下一阶段只允许设计独立的 Agent continuation 资格：
  从同源 checkpoint 重复执行冻结 Agent continuation，先估计方差、成本、恢复性和预算轨迹，再决定是否实现 controller。
- 发布状态：分支 `yiwei/427-dynamic-budget-trajectory-v5` 已推送；PR #428 堆叠在 PR #426 的分支之上并等待 CI/审查，
  不自动合并。
- 状态：Issue #425 的 `symlink-safe-checkpoint-restore-gate-v1` 工程门禁已通过，决定为
  `proceed_to_dynamic_budget_trajectory_qualification_v5_design`。恢复器继续使用 Python `tarfile.data_filter` 的成员路径、
  权限和特殊文件限制，只将 symlink 目标改为按成员父目录解析；hardlink 仍按 archive root 解析。所有内容先恢复到同级
  staging，完成解包后 containment 和 tree hash 校验后才原子发布 destination。
- 门禁证据：8/8 case 通过。合法 `src/.libs/libestr.la -> ../libestr.la` 保持原始 link target 并正确解析；真实相对
  越界、absolute symlink、越界 hardlink、character device、FIFO 和 tree-hash mismatch 均被拒绝且未发布 destination。
  v4 `libestr` checkpoint 的完整 tree hash 恢复前后同为
  `bf843bc282eabedefeb6e7ea053747a13944125c993660e61efa47a97d64fefe`，决策 tree hash 同为
  `1e712e8e560e9b8bf3f7f2845df3aac66d7c6103b3bb4e2feb247d8abcd2488f`。
- 历史完整性：门禁只读使用 v4 checkpoint，没有创建 continuation 或容器。门禁后 v4 evidence audit 仍为 1,797 files /
  34,453,974 bytes，inventory canonical SHA-256
  `e398003b48a2ded0b745900900481a21b2aa5879f3296ba71c06032f50e55294`。全程 0 credential、0 Provider、0 Agent。
- 当前边界：该结果只解除全新 v5 的 checkpoint restore 基础设施阻塞，不说明 v5 已通过，也不评价动态预算、Jev、
  Agent 或 controller 效果。下一步先设计并冻结 `dynamic_budget_trajectory_benchmark_qualification_v5` 的新 manifest、
  预注册、identity 和 create-once evidence；不得续跑、补齐或修改 v1-v4。
- 状态：Issue #423 的动态预算多步轨迹 benchmark 资格已在 v4 按规则停止，决定为
  `stop_before_agent_continuation_and_controller_implementation`。v1-v3 分别暴露 CMake 随机诊断名、未绑定的
  Docker hostname 和 Autoconf `autom4te.cache`；每个 identity 均 create-once 封口且 raw evidence 只读。
- v4 正向部分证据：CMake/Make 六个项目完整通过，Autotools `libestr` 的 configure/build 也通过，共 20 个完整
  连续状态、40/40 禁网 Docker continuation exit 0 且 successor 等价、20/20 checkpoint 六类哈希完整、20/20
  动作前/增量/动作后六维预算守恒。CMake/Make 两个 block 均消费 18 次执行，stop reservation 转移为 `2/2`；
  全程 0 credential、0 Provider、0 Agent，cleanup 后 0 managed container。
- v4 停止原因：恢复 `autotools-libestr-state-3` checkpoint 时，Python `tarfile` 的安全 `data` filter 将合法的
  `src/.libs/libestr.la -> ../libestr.la` 相对 symlink 误判为越出 destination；该状态尚未执行 continuation，后续
  `libfastjson/libev` 未观察、不填零。这是 checkpoint restore 基础设施失败，不是动态预算、Autotools action 或
  controller 的负效果。
- 当前边界：跨 CMake/Make/Autotools 的完整轨迹资格仍未通过，因此不设计 Agent Provider continuation、不实现
  controller。下一步先建立独立 symlink-safe restore engineering gate：按 symlink 所在父目录解析并拒绝真正越界、
  absolute、device/FIFO 等成员；门禁通过后才能冻结全新 v5 qualification，禁止续跑、补齐或修改 v1-v4。
- 状态：Issue #421 已完成 `cpp-dynamic-budget-identifiability-audit-v1` 只读审计，决定为
  `stop_before_dynamic_budget_controller_implementation`。8 项资格门槛仅输入/账本完整性与 matched 三策略覆盖
  2 项通过；在新的轨迹 benchmark 资格通过前，不实现动态预算 controller。
- 已有可用结构：Jev v6 的 12 个同源受控故障状态、72 个 arm 全部 ledger/result 哈希闭合，三策略各两次重复，
  CMake/Make/Autotools 各 24 arm；严格成功 45、失败 27。进展状态 v1 另有 409 个连续 observed-action 决策点，
  但按设计没有未选择动作结果。历史 4 个 checkpoint 能冻结环境与剩余安全预算，但干预不是
  `direct / escalate / stop`。
- 决定性缺口：v6 每个 arm 只有一个控制决策；16 个直接动作失败 arm 自动拼接 Agent；pure action 覆盖为
  direct 29、escalate 27、stop 0，且 `cc65` 没有 pure direct。72 个路由状态没有可恢复 checkpoint，也没有
  动作前/后六维预算快照；12 个项目均为结果已公开的 evaluation 数据，每任务预算不能跨项目再分配。
- 成本边界：71/72 arm 具有严格终点和完整总成本。`redis` repetition 2 的一次 Jev 请求因
  `TypeSafeAPIConnectionError` 结束，已知发生 1 次请求，但 input/output token 与费用未知；审计未估算回填。
- 解释边界：本结果不说明动态预算控制无效，只说明旧数据不能支持其离线训练、选择或效果评价。下一步先建立
  `dynamic_budget_trajectory_benchmark_qualification_v1` 候选：三种构建系统各 3 个新项目族、每项至少 3 个
  多步状态、每状态 2 次 clean checkpoint replay，显式记录动作前/增量/动作后预算并使用项目 block 共享预算；
  该资格通过前保持 0 Provider、0 Agent/Jev 调用。
- 状态：Issue #419 的 `cpp-jev-natural-failure-default-path-qualification-v1` 已完成唯一正式 attempt 和只读结果审计，
  最终决定为 `stop_before_reference_closure_qualification_v1`。不创建 reference closure、typed-action matrix 或
  自然失败 Provider 三臂 identity。
- 正式 observation：v4 冻结的 CMake、Make、Autotools 各 12 项全部执行两个 clean default-path replicate，
  共 36/36 项、72/72 observation 完成；分类为 23 个 `stable_failure_candidate`、5 个
  `stable_host_userland_closure`、5 个 `stable_non_host_target`、2 个 `stable_no_compiled_artifact` 和 1 个
  `network_dependency_excluded`。0 infrastructure failure、0 credential、0 Provider、0 model token，cleanup 后
  0 managed resource。
- 机械失败与审计边界：正式门槛错误要求已知非宿主项目不得保持 target-unresolved failure candidate，导致
  `gta-reversed` 触发机械 stop；该门槛比 v5 reference-closure 合同更严格，不能解释为 `gta-reversed` 已证明可在
  Linux 闭合。正式 report、marker 和 raw evidence 保持原样，不结果后改标签或重跑。
- 不可挽回的配额结论：CMake calibration 固定三个槽分别为默认路径直接成功的 `primesieve`、默认 endpoint 为
  Windows DLL 的 `gta-reversed`、kernel endpoint 的 `seL4`，所以 reference-eligible natural failure 上限为
  `0/1`。禁止 replacement、backfill 和角色前移，因此即使移除过严门槛，reference 阶段也不可能通过。
- 新构造效度缺口：`Hamlib` 默认构建生成大量宿主 x86_64 ELF/`ar`，却因 libtool 构建普通共享库时使用
  `-nostdlib` 被误判为 freestanding。v5 的无作用域 target-signal 优先级不能原样推广；未来若重启自然失败抽样，
  non-host 信号必须绑定具体 producer、产物或默认 endpoint。
- 当前工作类型：正式零 Provider 数据资格与只读结果审计，不是 treatment 实验。自然失败路线当前停止；受控失败
  Jev 正向结论和混合 Workflow 工程闭合结论不受影响，动态预算控制仍是尚未独立验证的下一研究候选。
- 状态：Issue #417 已完成 Linux build-closure v5 机制实现与非正式工程 canary。新门禁不再用 source-only
  平台标签决定资格；默认路径重复失败只形成 `stable_failure_candidate`，只有绑定同一默认 target 的 reference
  recipe 在两个 clean workspace 中均生成宿主 Linux 用户态 ELF/`ar`，且 source identity clean，项目才可进入
  自然失败角色。
- v5 工程 canary：10 个已人工审计 exact commit 各运行 2 次无网络 clean observation，共 20/20 有界终结，
  0 infrastructure failure、0 受管容器残留。分类为 5 个 `stable_non_host_target`、1 个
  `stable_host_userland_closure`、2 个 `stable_failure_candidate`、1 个 `stable_no_compiled_artifact` 和 1 个 timeout；
  0/10 成为 `qualified_natural_failure`。
- 构造效度信号：`SketchyBar` 的 Apple target、seL4 kernel contract、RB3Enhanced Windows toolchain、vitaGL
  console toolchain 和 Echo firmware/rootfs 均从实际默认路径直接识别；`gta-reversed` 在 CMake 版本门禁处提前
  失败，保守保持 target unresolved。旧 source false positive `opera-libretro` 两次生成 x86_64
  `opera_libretro.so`；`rakupp` 进入实际宿主编译但在 120 秒命令预算内 timeout，没有再被静态误排。
- 工程修复中的失败证据：首轮 canary 曾把 CMake 的 `CMakeDetermineCompilerABI_CXX.bin` 当作项目产物，使
  `fast_float` 假闭合；该轮不作为通过证据。修复并新增回归后，最终轮将其正确分类为
  `stable_no_compiled_artifact`。收紧 producer 合同后的最终聚焦测试为 26 passed，包括真实 gcc/ar、foreign ELF、
  PE/Mach-O、probe 排除、producer 绑定、默认 target reference 绑定和 Docker clean build。
- 当前工作类型：工程修复与机制资格，不是 treatment 数据收集。版本化 summary 明确标为
  `nonformal_engineering_canary`；临时 raw observation 未发布为 formal evidence，因此本结果不支持全量候选通过率、
  自然失败角色配额、Jev/Agent 效果、成本收益或动态预算结论。
- 下一决策：设计独立 formal build/reference qualification identity，把 v4 source-only 输出只作为候选和风险信号，
  对更大的冻结候选池执行默认路径双观察、默认 target reference 双闭合与 Forge verifier；通过后才分配
  design/calibration/evaluation 角色。不得回写或续跑 v1-v4 identity。
- 状态：Issue #415 的 Linux applicability v4 唯一正式 source-only attempt 已完成。机械决定为
  `proceed_to_natural_failure_build_reference_qualification_v4`，但只读构造效度审计发现双向分类错误，后验决定为
  `stop_before_natural_failure_build_reference_qualification_v4`；不得创建后续 build/reference identity。
- v4 正式证据：800 个搜索结果排除 214 个历史命中后完成 586/586 个未见候选，245 项 source eligible，
  0 infrastructure failure；eligible edge 为 CMake 141、Make 97、Autotools 39，机械唯一分配为 `12/12/12`。
- v4 构造效度：对 5 条正式排除和 36 条 reserve 全量复核，107 个 exact-commit 入口/文档 blob 的 Git SHA 与
  内容 SHA-256 全部匹配。排除项中 `ash/rakupp`、`libretro/opera-libretro` 为 2 个明显误伤；reserve 中
  `gta-reversed/gta-reversed`、`seL4/seL4`、`RBEnhanced/RB3Enhanced`、`Rinnegatamante/vitaGL`、
  `Gamer92000/echo-dot-assist` 为 5 个明显误纳入。
- 失败机制：v4 能剥离注释并识别部分 Linux 文档，但仍没有解析默认条件分支、默认 target 依赖闭包和编译器目标。
  非默认分支中的 Apple/裸机信号仍会误伤多平台项目，规则表之外的 kernel、console、Android NDK 和 Windows DLL
  又会落入 `portable_entry_without_exclusive_signal`。继续扩充关键词不能解决作用域问题。
- 当前工作类型：v4 结果分析与下一资格机制设计。source-only 阶段应降级为高精度候选发现和风险标注；默认构建
  路径、目标架构与 Linux 用户态 ELF/`ar` 闭合必须在隔离的零 Provider build/reference qualification 中确认，
  严格 verifier 继续作为最终裁判。
- v4 边界：591 个 evidence 文件共 1,488,806 bytes，inventory canonical SHA-256 为 `0d08616e...e6bc`；全过程
  0 build、0 Docker、0 credential read、0 Provider request、0 model token。v1-v4 正式 report、marker 和 raw
  evidence 全部只读；本结果不评价 Jev、Agent、自然失败成功率、成本或动态预算控制。
- 状态：Issue #413 的 source catalog 与双 clean build qualification 已完成；生成 build gate 机械通过，但 reference 前构造效度审计证明 Make calibration 配额不可能满足，最终决定为 `stop_natural_failure_evaluation_v2_before_reference_recipe`。
- 当前工作类型：数据资格结果与只读构造效度审计。catalog 从 120 个搜索结果排除 11 个历史项目后得到 109 个未见候选；53 个 source eligible，最终为 CMake、Make、Autotools 各冻结 8 个互不重复的项目族。
- source catalog 证据：109/109 仓库项目级终结，0 infrastructure failure；30 项因 `.gitmodules` 排除、23 项缺少根入口、3 项命中根入口网络获取信号。attempt 用时约 336 秒，114 个 evidence 文件共 197,527 bytes，inventory canonical SHA-256 为 `d561e612...59736`。
- build qualification 证据：24/24 项完成，生成分类为 17 个稳定失败、6 个初始成功、1 个运行时网络依赖排除；机械角色计数为 CMake `1/1/3`、Make `1/1/4`、Autotools `2/1/3`。434 个 evidence 文件共 736,283 bytes，inventory canonical SHA-256 为 `d2c61123...1d658`，全部 cleanup 且 0 受管容器。
- v2 停止原因：Make calibration 只有 `sogou/workflow` 初始成功和 `SketchyBar` 稳定失败；后者唯一构建入口固定 Apple target、framework 与 Mach-O/lipo，无法在冻结 Linux ELF/`ar` 严格终点形成 reference closure。reference-eligible 配额上限为 `0/1`，角色不可前移或替换。
- v2 边界：0 credential read、0 Provider request、0 model token、0 reference recipe、0 action matrix；它不支持对 Jev 自然失败能力作正负判断。Issue #411 及更早 evidence 永久只读。
- v1 状态：Issue #411 已完成自然失败 source qualification v1 的结果盲设计、实现、唯一正式 attempt 和只读失败审计；决定为 `stop_natural_failure_evaluation_v1`，不进入 reference recipe、动作矩阵或 Provider 三臂实验。
- v1 工作类型：数据资格与失败结果分析。v1 计划从 CXXCrafter Top100 的 22 个未见 exact commit 构造跨 CMake/Make/Autotools 自然失败；attempt 在完成 7 项后因 `rpcs3` submodule timeout 被 runner 错误提升为全局失败而封口。
- 自然失败关键证据：7 个完成项中，5 个与冻结根入口合同不符；runner 标为稳定失败的 `flameshot`、`kvrocks` 均是禁网下 `FetchContent` 失败，按预注册网络排除项复核后，有效稳定自然失败为 `0/7`。固定 CMake calibration 两项均 root-entrypoint ineligible，配额 `0/1`，剩余任务无法改变停止结论。
- 自然失败证据边界：Make/Autotools 和其余 CMake 候选未观察，不记零；本轮不支持 Jev/Agent 自然失败效果、reference/action 多样性、成本收益或动态预算结论。全过程 0 credential / 0 Provider / 0 token / 0 reference recipe / 0 action matrix，cleanup 后 0 受管容器。
- 上游正式结果：Issue #408 的受控失败正式比较中，严格成功为 `JevGate+Agent 22/24`、`AlwaysAgent 10/24`、`RuleGate+Agent 13/24`；Jev 相对 AlwaysAgent 的成功率差为 `+0.500`，项目族聚类 bootstrap 单侧 95% 下界为 `+0.292`，Provider 估算成本下降 `89.6%`。
- 混合链路结果：零 Provider qualification v3 在 CMake、Make、Autotools 上 `3/3` 严格成功；真实 canary 也为 `3/3` S0-S5 严格成功、全部 cleanup、0 受管资源。Jev 对 CMake/Autotools 直接执行 `configure/dependency`，Make 的冻结候选前置条件失败后由真实 Agent 接管并把控制权交还 Workflow。
- canary 用量：Jev 为 3 requests / 4,146 input tokens / `$0.000174132`；Agent handoff 为 1 次、9 requests / 86,160 recorded tokens。10 个 evidence 文件共 132,192 bytes，inventory canonical SHA-256 为 `6b6424f65603bc0d9a1b4c379fa7ad37206cbe6f437bd50395512c8586b4b859`。
- 当前研究边界：Issue #409 只证明真实 Provider 接线、控制权交还、固定安全预算、严格终点和 cleanup 闭合。三个 case 来自既往受控故障，Make 还人为强制 handoff；因此不支持自然失败成功率、成本收益、模型排名、未见项目泛化或动态预算控制。
- 当前机制定位：Workflow 持有状态、预算和严格终点；Jev 只选择代码绑定 typed action；异常、低置信、合同错误或前置条件失败均升级 Agent；Agent 返回后重新读取权威状态。偏序义务状态 v1 已停止，动态预算控制仍是独立待验证候选。
- 阶段 0 冻结问题：能否构造跨 CMake、Make、Autotools 的进展状态，使其在未见项目族和未来时间段中比轮次、token、阶段和错误类别等简单特征更能解释短期状态转移，并为后续预算动作实验提供足够的增量信息？
- 当前方向文档：`docs/research/2026-10-06-automated-compilation-innovation-landscape.md`。
- Jev 阶段 A 预注册：`benchmarks/preregistrations/cpp-typed-action-benchmark-qualification-v1.md`。
- Jev 阶段 A 资格报告：`benchmarks/reports/cpp-typed-action-benchmark-qualification-v1.md`。
- Jev RuleGate 可辨识性审计：`benchmarks/reports/cpp-typed-action-benchmark-rule-gate-audit-v1.md`。
- Jev v2 预注册：`benchmarks/preregistrations/cpp-typed-semantic-routing-pilot-v2.md`。
- Jev v2 资格报告：`benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.md`。
- Jev 离线资格 candidate 预注册：`benchmarks/preregistrations/cpp-jev-offline-qualification-candidate-v1.md`。
- Jev 离线资格 formal 预注册补充：`benchmarks/preregistrations/cpp-jev-offline-qualification-v1-execution-amendment.md`。
- Jev 离线资格失败报告：`benchmarks/reports/cpp-jev-offline-qualification-v1.md`。
- Jev v4 模型目录门禁报告：`benchmarks/reports/cpp-jev-offline-qualification-v4.md`。
- Jev v5 概率合同失败报告：`benchmarks/reports/cpp-jev-offline-qualification-v5.md`。
- Jev v6 离线资格结果：`benchmarks/reports/cpp-jev-offline-qualification-v6.md`。
- Jev controller replay v2 预注册：`benchmarks/preregistrations/cpp-jev-controller-replay-qualification-v2.md`。
- Jev controller replay v2 结果：`benchmarks/reports/cpp-jev-controller-replay-qualification-v2.md`。
- Jev 端到端 canary v7 预注册：`benchmarks/preregistrations/cpp-jev-end-to-end-canary-v7.md`。
- Jev 端到端 canary v7 结果：`benchmarks/reports/cpp-jev-end-to-end-canary-v7.md`。
- Jev 正式三臂比较 v6 预注册：`benchmarks/preregistrations/cpp-jev-formal-comparison-v6.md`。
- Jev 正式三臂比较 v6 资格报告：`benchmarks/reports/cpp-jev-formal-comparison-v6-qualification.md`。
- Jev 正式三臂比较 v6 结果：`benchmarks/reports/cpp-jev-formal-comparison-v6.md`。
- 混合链路设计：`docs/superpowers/specs/2026-10-11-jev-hybrid-workflow-design.md`。
- 混合链路实施计划：`docs/superpowers/plans/2026-10-11-jev-hybrid-workflow.md`。
- 混合链路零 Provider qualification v3：`benchmarks/reports/cpp-jev-hybrid-workflow-qualification-v3.md`。
- 混合链路 Provider canary v1：`benchmarks/reports/cpp-jev-hybrid-workflow-canary-v1.md`。
- 自然失败 source qualification v1：`benchmarks/reports/cpp-jev-natural-failure-source-qualification-v1.md`。
- 自然失败 source qualification v1 失败审计：`benchmarks/reports/cpp-jev-natural-failure-source-qualification-v1-failure-audit.md`。
- 自然失败 source catalog v2 设计：`docs/superpowers/specs/2026-10-11-jev-natural-failure-source-catalog-v2-design.md`。
- 自然失败 source catalog v2 预注册：`benchmarks/preregistrations/cpp-jev-natural-failure-source-catalog-v2.md`。
- 自然失败 source catalog v2 结果：`benchmarks/reports/cpp-jev-natural-failure-source-catalog-v2.md`。
- 自然失败 build qualification v2 结果：`benchmarks/reports/cpp-jev-natural-failure-source-qualification-v2.md`。
- 自然失败 build qualification v2 构造效度审计：`benchmarks/reports/cpp-jev-natural-failure-source-qualification-v2-construct-audit.md`。
- 自然失败 Linux applicability v3 设计：`docs/superpowers/specs/2026-10-12-jev-natural-failure-linux-applicability-v3-design.md`。
- 自然失败 Linux applicability v3 预注册：`benchmarks/preregistrations/cpp-jev-natural-failure-linux-applicability-v3.md`。
- 自然失败 Linux applicability v3 结果：`benchmarks/reports/cpp-jev-natural-failure-linux-applicability-v3.md`。
- 自然失败 Linux applicability v3 构造效度审计：`benchmarks/reports/cpp-jev-natural-failure-linux-applicability-v3-construct-audit.md`。
- 自然失败 Linux applicability v4 设计：`docs/superpowers/specs/2026-10-12-jev-natural-failure-linux-applicability-v4-design.md`。
- 自然失败 Linux applicability v4 预注册：`benchmarks/preregistrations/cpp-jev-natural-failure-linux-applicability-v4.md`。
- 自然失败 Linux applicability v4 结果：`benchmarks/reports/cpp-jev-natural-failure-linux-applicability-v4.md`。
- 自然失败 Linux applicability v4 构造效度审计：`benchmarks/reports/cpp-jev-natural-failure-linux-applicability-v4-construct-audit.md`。
- Linux build-closure v5 设计：`docs/superpowers/specs/2026-10-12-linux-build-closure-qualification-v5-design.md`。
- Linux build-closure v5 实施计划：`docs/superpowers/plans/2026-10-12-linux-build-closure-qualification-v5.md`。
- Linux build-closure v5 工程 canary：`benchmarks/reports/cpp-jev-natural-failure-linux-build-closure-canary-v5.md`。
- Jev API 合同审计：`docs/research/2026-10-09-jev-api-contract-audit.md`。
- 三候选机制审计：`docs/research/2026-10-09-three-candidate-mechanism-audit.md`。
- 主动诊断机制审计：`docs/research/2026-10-09-active-diagnosis-mechanism-audit.md`。
- 阶段 0 预注册：`benchmarks/preregistrations/cpp-cross-build-progress-state-qualification-v1.md`。
- 阶段 0 结果：`benchmarks/reports/cpp-cross-build-progress-state-qualification-v1.md`。
- 历史方向与审计：`docs/research/2026-09-29-automated-compilation-thesis-direction.md`、`docs/research/2026-09-29-contract-driven-repair-design-audit.md`。

## 文献定位

本轮定向检索覆盖 CXXCrafter、CompileAgent、BuildBench、Repo2Run、GradleFixer、EnConda-Bench、
EvoConfig、ComBench、PhantomRun、EvidenT，以及 SWE-Replay、EET、FailFast、XRepoSkill、SetupX、
BootstrapAgent、SWE-Skills-Bench、VibeMemBench 等轨迹控制、动作接口和经验迁移工作。

已确认不能单独作为新贡献的表述：

- 用 LLM/Agent 自动编译 C/C++，或在固定 Workflow 中加入 Agent；
- 多 Agent 讨论、原始日志反馈、迭代修复和证据历史；
- 独立 verifier、任务规格、分层成功判据和 clean replay；
- 增加领域专用工具、更多推理轮次或更多并行采样；
- 只报告成功率、成功案例平均时间、token 或费用。

三候选审计曾保留**跨构建系统、由可执行证据构成、允许回退的偏序构建义务状态**，但阶段 0 没有验证出其相对
简单特征的预注册增量价值。后续主动诊断审计又确认，竞争假设、主动测试、信息增益、成本动作选择和停止已有直接
先例；把它们用于构建系统主要是场景迁移。过程评价、早停、checkpoint 分支、domain-specific tools 和跨仓库经验
迁移也已有直接先例。本次检索不是系统综述，不能声称全球首次或排除所有更窄的机制空白。

## Forge 已有证据

- Forge 已具备 Compile Session、failure checkpoint、严格 candidate/functional/provenance 判定、external evaluator、ledger 和 clean replay，可作为新控制策略的统一执行与测量基础。
- Stage C v8 四任务 strict、S0-S5、bitwise 和 cleanup 均为 4/4；37 requests / 279,988 tokens。它是工程 canary，不是方法比较。
- 历史 behavioral v2 为单 CMake controlled fault，baseline 3/6、treatment 5/6；multi-checkpoint v3 为同一 fault family，baseline 4/6、treatment 6/6。两者只支持探索性假设。
- Opaque provenance replication 为 12/12 pairs 终结、7/12 endpoint-censored；baseline 0/12、treatment 6/12，只有 5 个 eligible pairs，`primary_test=null`。
- Runtime v3 三臂 qualification 在 delivery/target 与 provenance 两个真实 Docker parent checkpoint 上闭合 candidate、oracle、external evaluator、clean replay 和 cleanup。它只证明基础设施可执行。
- Mechanism v2 唯一 formal batch 在 12/36 arms、4/12 checkpoints 后因 `lz4` target-mapped artifact 基数不兼容永久失败。冻结 evidence 为 70 files / 689,742 bytes，inventory SHA-256 `5c885b2a...b9d11`，75 requests / 1,068,534 total tokens，失败后 0 managed resources。
- Mechanism v2 的两个完整项目中，delivery/target 三臂均成功，provenance 三臂均为 0；其余 8 checkpoints 不填零，三个比较的识别区间均为 `[-2/3, +2/3]`，`primary_test=null`、`secondary_test=null`。
- 当前证据链表现为：单一 delivery fault 的早期 pilots 有正向探索信号；扩大到 provenance 后可辨识性不足；mechanism v2 已完成的四个 checkpoints 由 fault stratum 而非反馈条件区分。它支持停止该主线，不支持“反馈无效”或等效性结论。
- 进展状态 v1 使用 6 个开发项目族/100 个决策点和 12 个未来未见项目族/309 个决策点；两组均观察到四类转移。12 点人工重建的 216 个 obligation 字段、24 个诊断字段和转移标签一致率均为 1.0。
- `progress_state` 相对 `simple_combined` 的项目族宏平均 log loss 差值为 `-0.0016` nat，bootstrap 95% 区间为 `[-0.1033, 0.1143]`，仅 7/12 项目族改善；Make 改善 `-0.1390`，CMake 恶化 `+0.0133`，Autotools 恶化 `+0.1059`。最小改善、区间和跨系统三项门槛失败。
- 主动诊断资产审计覆盖阶段 0 的 30 条 session、18 个项目族和 409 个决策点。264 个 `diagnostic` 动作中有 256 条逐字不同的 Shell 命令；每个状态只观察原策略选择的一个动作，且 manifest 没有独立根因标签，因此不能估计替代探针的信息价值或反事实效果。
- Jev 阶段 A 使用 CMake/Make/Autotools 各 8 个 project family，按 exact commit 时间严格切为 6 个 design、6 个 calibration、12 个 evaluation；每项目构造 5 个状态、每状态 3 个代码绑定动作。48 个 reference build/oracle closure 和 720 次候选动作执行全部闭合，360/360 state/action pair 的 categorical replay 一致，旧 409 点目录覆盖为 409/409。
- Attempt 1 在 `libuv` functional oracle 因 `-std=c11` 隐藏 `pthread_rwlock_t` 后停止并冻结失败记录；Amendment 1 只将该 oracle 改为 `-std=gnu11`，不复用部分 outcome，attempt 2 从全新目录完整重跑并通过。
- 资格通过不等于研究问题可辨识。冻结 RuleGate 只读 `phase_facts` 与候选动作族，在 CMake、Make、Autotools 各 40/40 状态、evaluation 60/60 状态上均为 top-1 安全率 100%、直接执行覆盖 100%、错误率 0%；48 个状态还有两个合格动作。阶段 B 要求同风险下比 RuleGate 多 10 个百分点覆盖，最大可能提升为 0，因此不调用 Jev。
- Jev v2 使用 6 个未进入 v1 的 project family，CMake/Make/Autotools 各 2 个；每项目构造缺失编译输入、失效构建状态和错误 target 三类故障，向路由器暴露完全相同的 phase facts 与动作顺序。12/12 reference closure、144/144 action branch 有界终结，72/72 pair 的 categorical replay 一致；由 strict success 与冻结成本重建的最优动作中，`dependency`、`configure`、`build` 各为 6/18，并各覆盖全部 6 个 project family。
- v2 RuleGate 固定选择 `build`，top-1 与 route-acceptable coverage 均为 `0.3333`，通过 75%/90% 难度门槛；LOPO TF-IDF/逻辑回归为 17/18（`0.9444`），以 1 个样本低于 95% 停止线。唯一错误是 held-out `numactl` 的缺失 `libnuma.c` 状态被判为 `build`。v2 按规则进入 Jev 离线资格，但文本基线已接近饱和，不能据此预期 Jev 会有明显准确率增益。
- Issue #393 已核对 TypeSafe 官方 Quick start、API、Models、Confidence、Choice、State、Python SDK、RetryPolicy 和 Jev 1.13 jaggedness。SDK mock 验证了 `/v1/systemone`、Bearer 鉴权、固定模型、request ID、usage、Choice 概率与 confidence；529 错误在 `max_retries=0` 下只有一次物理请求。Candidate、v2 和阶段 A 相邻回归为 21 passed、2 个显式 Docker gate skipped。
- Issue #395 formal manifest canonical SHA-256 为 `e98b6b3e3a485ca26f3185491f460cc5a6b447f64d7a15d5fac9fcf72daf6616`。零 Provider outcome collection 在 `zstd` calibration replicate 1 的 `missing_compile_input` 处失败关闭；failure evidence 共 20 files，inventory canonical SHA-256 为 `b1c52c54b5ccae8b6e21a841df480fdaba3415d333ee007a937688eba75633fb`。未读取 `jev-apikey.txt` 内容，未创建 Provider evidence。
- Issue #399 v4 的 `/v1/models` 只列出 `jev-latest` 和 `jev-preview`，目录门禁因未显式列出 `jev-1.13.0` 而在 0 模型请求下失败；后续 v5 证明固定版本可以直接调用，因此 v4 是 availability 假阴性，不是模型能力结果。
- Issue #400 v5 成功调用固定 `jev-1.13.0` 并保存 12 个 design 响应；第 13 个响应因序列化概率和超出原 `1e-6` 容差而失败关闭。13 次请求、11,826 input tokens、1,212 output tokens、费用 `$0.000496692` 均被保留，v5 不续跑。
- Issue #401 v6 将原始概率和容差预先冻结为 `0.005`，保存原始值并归一化后分析。Design round 1 为 10/18 top-1、18/18 安全路由、17/18 顺序一致；唯一获准的 prompt 修订后，design round 2 为 18/18 top-1、安全路由和顺序一致。
- v6 calibration 为 18/18 top-1，零观察错误阈值为 `0.6747568477098429`；evaluation 为 18/18 top-1、18/18 顺序一致、18/18 校准后直接执行和 0 次错误，CMake/Make/Autotools 各 6/6。Macro-F1 为 `1.0`、multiclass Brier 为 `0.0003222222`、ECE 为 `0.0072222222`。
- 同一 evaluation 上，固定 `build` RuleGate 为 6/18，TF-IDF/逻辑回归为 17/18。Jev 通过预注册门槛，但 prompt 已明确编码三类受控故障语义，且轻量文本基线接近饱和，不能将 18/18 解释为通用模型优势。
- Issue #403 的 controller replay v1 在首个 `choice_probability_mismatch` 场景按协议失败并永久停止。控制器实际安全升级，但故障夹具概率和为 0.9，先触发 `probability_contract_invalid`；只读全矩阵诊断为 324/324 升级、0 错误直接动作、0 executor 调用，不能替代新的 formal identity。
- Issue #404 v2 只修正故障夹具可辨识性，不修改控制器、阈值、父样本或通过门槛。正式回放复现正常路由 18/18，18/18 调度均等待严格验证，324/324 故障以冻结理由升级，错误直接动作和故障 executor 调用均为 0；CMake/Make/Autotools 各 6 个状态，v1/v6 evidence inventory 前后不变。
- Issue #406 的 v1-v6 依次暴露父常量、workspace、宿主权限、build-system identity、artifact role 和公开头文件 staging 问题，均保持只读。v7 零 Provider qualification 为 3/3 strict；正式 canary 中 JevGate 为 3/3 strict、0 Agent 请求，AlwaysAgent 为 1/3 strict、39 请求/440,480 tokens，RuleGate+Agent 为 1/3 strict、23 请求/238,067 tokens。Jev 三次请求均直接执行且严格通过，总费用 `$0.000174804`。
- Issue #408 的 v1-v5 资格失败分别暴露 source snapshot、权限、fault compatibility、artifact closure 和 Redis 可复现 header 问题，均冻结只读；v6 零 Provider qualification 为 12/12 strict。正式 72-arm 比较中 JevGate、AlwaysAgent、RuleGate+Agent 分别为 `22/24`、`10/24`、`13/24` strict；Jev 相对 AlwaysAgent 的项目族聚类单侧 95% 下界为 `+0.292`，成本下降 `89.6%`，联合门槛通过。
- Issue #409 的 qualification v1/v2 分别因不存在的取证字段和 Autotools oracle 错误而按规则冻结失败；v3 在三种构建系统上 `3/3` strict，2 次直接动作、1 次 scripted Agent handoff。真实 Provider canary 随后 `3/3` strict，观察到 2 次直接动作和 1 次真实 Agent handoff，控制权交还、预算、S0-S5、cleanup 和零资源门禁全部通过。
- Issue #411 的 source qualification v1 完成 7/22 项后因 runner 未捕获 `rpcs3` submodule timeout 而失败封口。原始分类为 5 项 source-contract ineligible、2 项 stable failure；只读协议审计确认后两项实际是禁网导致的 CMake FetchContent 失败，故有效自然失败为 0/7。CMake calibration 固定两项均 ineligible，预注册 `>=1` 门槛已不可达到；42 个 evidence 文件共 49,680 bytes，inventory canonical SHA-256 为 `fcb426ed...cd9c8b`，0 Provider 且 cleanup 闭合。

## 当前研究决策

- 保留合同作为严格裁判，不再把合同 feedback exposure 当作主要修复机制。
- 不修复 `lz4` checkpoint，不继续 mechanism v2 剩余 24 arms，不建立 replacement identity。
- 旧 C0/T1/T2 evidence 永久只读，可作为探索性负结果和研究转向依据，不能解释为 treatment effect。
- 三候选机制审计后的唯一优先候选已完成资格审计并失败；当前偏序进展状态机制按预注册永久停止。typed action 仍只作为支撑动作层；此前审计的跨仓库经验迁移没有形成足够的新机制。
- Issue #382 只读资格审计已完成；不得结果后调整切分、阈值、义务、诊断模式或模型来挽救 v1。
- Issue #385 主动诊断候选按 `abandon_active_diagnosis_as_novel_mechanism` 停止；不把已有 hypothesis/EIG/POMDP/cost-aware testing 组合重新表述为 Forge 新机制。
- Issue #389 阶段 A 的 `proceed_to_jev_offline_qualification` 只表示 benchmark 可执行门槛通过；后续零 Provider RuleGate 审计覆盖该进入决定，当前最终决定为 `stop_jev_provider_qualification_and_redesign_benchmark`。
- 不在已被 RuleGate 完全解出的阶段 A v1 上调用 Jev 或实现 controller；该停止决定保持不变，v6 使用的是另一个具有异最优动作标签的受控故障 benchmark。
- 当前 v1 的 evaluation split 已被 RuleGate 审计暴露，不能在修订动作或状态后继续作为确认性模型评测集。Issue #391 v2 使用了 6 个新项目族，但它是受控故障难度 pilot，不是时间后移的确认性模型评测；后续 Provider 评测必须另行冻结项目族与时间隔离，或把 v2 锁定为一次性 evaluation 并使用完全独立的 design/calibration 数据。
- Issue #391 v2 已按冻结规则通过零 Provider 难度门禁，决定为 `proceed_to_jev_offline_qualification`；该决定只授权规划独立的 Jev 离线资格 identity，不把 #391 转成 Provider 实验，也不允许修改或重跑 v2 outcome。
- Issue #393 candidate 只冻结后续 Provider 实验的前置合同，不是 formal Provider attempt。使用固定 `jev-1.13.0`，同一请求包含动作正序与逆序 Choice，SDK retry 为 0，总预算候选为 72 请求、1,000,000 input tokens、0.042 美元。
- Issue #393 的 evaluation 做到项目族隔离，但不满足全局 commit 时间后移，且 v2 标签对研究者可见；后续结果只能解释为冻结受控故障 holdout，不能支持跨时间、自然失败总体或开放世界泛化。
- Issue #395、#399、#400 与 #401 均已消费且永久只读，禁止重跑、续跑、补齐、替换或覆盖 evidence。v4/v5 的基础设施失败和 v6 的正向资格结果必须同时保留。
- v6 决定为 `proceed_to_controller_replay_qualification`，Issue #404 v2 决定为 `proceed_to_end_to_end_canary`，Issue #406 v7 决定为 `proceed_to_formal_end_to_end_comparison_design`；Issue #408 v6 已以独立未见项目族正式比较得到 `supports_jev_controlled_failure_claim`。
- `cpp-jev-formal-comparison-v1` 至 `v6` 及全部资格、正式 evidence 已消费并永久只读；禁止重跑、续跑、replacement、backfill 或结果后修改阈值。正式结果确认 Jev 类型化语义路由达到当前硕士论文的领域方法与系统实证门槛，但不主张通用路由机制首创。
- 项目族与时间隔离属于所有候选的评测纪律，不单独构成经验迁移的新机制。
- Issue #409 已冻结为 `proceed_to_natural_failure_evaluation_design`；其 qualification、canary manifest、报告和 raw evidence 均已消费并永久只读，禁止重跑、续跑、replacement 或 backfill。
- Issue #411 v1 决定为 `stop_natural_failure_evaluation_v1`；失败 attempt、marker、日志和生成报告永久只读，禁止续跑、replacement、backfill 或改写标签。若继续自然失败路线，必须先用新的 source-only catalog 验证根入口、递归 submodule 成本和离线依赖闭包，再在新 Issue/identity 中分层；本次部分结果不得进入 treatment 分母。
- Issue #419 默认路径资格 v1 的正式 report、marker、273 个 evidence 文件和结果审计永久只读；CMake calibration
  reference-eligible 上限为 `0/1`，决定为 `stop_before_reference_closure_qualification_v1`。不得创建其 reference
  子 identity、移动角色或用 replacement/backfill 挽救。若未来重新抽样，必须使用新的候选池、角色和 identity，
  并先修复 target signal 与 producer/endpoint 的作用域绑定。
- 动态预算控制仍属于整体机制候选，但尚未独立验证；Issue #408/#409 均不能用于宣称预算控制有效。Issue #409 的固定安全预算只用于验证控制权交还和严格终点。
- 新实验必须重新冻结有限预算向量、开发/测试项目隔离、严格成功、删失效率指标、最小有意义效应和分析顺序；旧 identity 的“无 token ceiling”不沿用为成本研究设计。

## 解释边界

当前证据可以支持：

- 合同裁判能提供比 Shell exit code 更严格、可复现的自动化编译终点；
- 固定 Flow、动态交互和重复尝试在既有论文中通常比一次性生成更强，但更多轮次并不保证单调收益；
- 失败轨迹可能主导时间和 token 成本，因此预算分配是有实际依据的研究问题；
- Forge 现有只读轨迹足以重建 v1 进展状态并执行项目族/时间隔离的 observed-action 资格审计；
- 在固定语料、特征、模型和门槛下，v1 进展状态没有足够的独立转移信息来支持后续预算动作实验。
- Forge 现有轨迹能描述已执行的诊断过程，但缺少同状态替代动作结果与独立根因，不能支持主动诊断动作价值估计。
- Forge 已能执行跨三种构建系统的闭集候选动作 outcome matrix，并在隔离副本中获得可重复标签；这是 benchmark 基础设施证据。
- 当前 v1 的确定性阶段事实已经完全决定安全推进动作，语义日志没有可测的增量决策空间，不能用于评价 Jev 相对 RuleGate 的提升。
- v2 在相同阶段事实下形成了跨三种构建系统的异最优动作标签，证明语义失败日志相对 coarse RuleGate 有决策信息；它支持测试 Jev 的动作判断，不支持 Jev 已有效。
- Forge 已具备与官方 Jev API 对接的确定性请求/响应适配和失败关闭 mock，且可以在不读取真实 credential 的情况下验证模型版本、概率、confidence、usage、request ID、顺序与零 retry 合同。
- 固定 `jev-1.13.0` 在 v6 的一次性受控故障 evaluation 上正确选择 18/18 个最低成本安全动作，正反候选顺序 18/18 一致；项目族隔离校准以 18/18 覆盖获得 0 次观察错误。
- v6 的正式模型调用满足 72 请求、1,000,000 input tokens 和 `$0.042` 的冻结预算上限，实际为 72 请求、83,210 input tokens 和 `$0.00349482`。
- 冻结 v6 响应可通过最小控制器复现 18/18 路由；控制器只执行代码绑定候选，不能生成 Shell 或宣告终态成功，并在 324/324 个冻结故障回放中升级 Agent、零故障 executor 调用。
- v7 canary 证明同一控制器可在真实 Shell 和严格终点下闭合三种构建系统；Jev 的 `configure/build/dependency` 三次直接执行均严格成功，并在该三项目 canary 中避免完整 Agent 调用。
- Issue #408 的正式比较支持：在冻结的 12 个未见项目族、三类受控构建失败、固定 `jev-1.13.0` 和当前校准阈值下，JevGate 相对 AlwaysAgent 同时满足严格成功非劣与 Provider 成本下降。21/21 次 Jev 直接动作通过严格终点，且 CMake、Make、Autotools 均无系统性退化。
- Issue #409 的最小混合协调器可在真实 Provider 条件下完成 Jev 直接动作、Agent 升级、权威状态重读、S0-S5 严格验收和 cleanup；callback 自报成功不能绕过 observer 的严格终点。
- Issue #419 在 36 个固定项目、72 次 clean observation 中得到 23 个稳定失败候选，说明候选失败本身并不稀缺；
  但固定 CMake calibration 的 reference-eligible 上限为 `0/1`，当前样本和角色无法支撑自然失败三臂实验。
- 默认路径动态执行能识别多类真实 endpoint，但仅凭完整日志任意位置出现 `-nostdlib` 等信号会误判普通宿主
  libtool 构建；target 信号需要与 producer、产物和默认 endpoint 建立作用域关系。

当前证据不能支持：

- 进展感知预算控制优于固定 Flow，或任何具体节省比例；
- 所有可能的进展状态表示都无效，或 v1 在更广项目总体、其他模型和新轨迹上必然无增量；
- 任何未选择动作的反事实效果、动作选择改进或 controller treatment effect；
- 主动诊断对自动化构建没有产品或 benchmark 价值，或世界范围不存在更窄的构建诊断机制空白；
- 结构化合同反馈的总体效应、统计显著性、无效或等效；
- Forge 整体优于 CXXCrafter、CompileAgent、BuildBench 或其他系统；
- Provider/模型能力排名，或 verifier、路由、搜索、领域工具的通用首创性；
- 从成功案例均值推断总体时间/成本，或把 canary/qualification 当作 treatment evidence。
- v6 之外自然失败、开放世界、跨时间数据上的 Jev 准确率或校准迁移，以及任何通用模型排名；当前 evaluation 是 6 个项目族、三类受控故障。
- Jev 在自然发生的构建失败、开放动作空间、更多构建系统或其他 Provider/模型上的严格成功非劣与成本收益；Issue #408 只覆盖冻结的受控失败与当前样本总体。
- Issue #408 不能证明动态预算控制或进展状态 v1；Issue #409 已证明 `workflow + agent + Jev` 工程链路可闭合，但不能证明它在自然失败上的成功率非劣、成本下降或动态预算有效。
- Jev 相对规则或轻量文本分类器具有稳定的实质增量；当前 TF-IDF/逻辑回归已达到 17/18，且 prompt 修订编码了三类故障语义。
- v2 在自然发生的真实失败总体中也有相同准确率、标签分布或可迁移性；当前只是 6 个项目、三类受控故障的资格 pilot。
- Issue #393 的 SDK mock 本身不能说明真实 API 能力；真实 API 可达、固定模型执行和离线选择结果由 v5/v6 单独证明，但仍不能说明 controller 能节省成本。
- Issue #395 的数据资格失败不能说明 Jev 选择正确或错误，也不能用于估计 calibration/evaluation 指标；唯一正式结论是当前 zstd fault fixture 不合格且 Provider 阶段被正确阻断。

## 当前允许与禁止

允许：

- 只读核验论文、公开实现、仓库报告、manifest、ledger 和冻结 evidence；
- 编写、审阅和发布 Issue #381 的版本化研究综述与状态交接；
- 对进展状态、typed action abstraction 和跨仓库经验迁移做文献与机制比较；
- 发布并审阅 Issue #382 和 #385 的版本化报告，保持失败结果与冻结输入可重建；为下一研究问题重新做文献与机制审计。
- 只读核验 Issue #389/#391/#393/#395/#399/#400/#401/#403/#404/#406/#408/#409 的 manifest、报告与冻结 evidence。
- 设计自然失败对照实验，明确样本来源、项目族和时间隔离、三臂基线、预算、停止规则、主要 estimand 与最小有意义效应；冻结新 identity 前不采集新数据。
- 设计独立的动态预算控制资格问题，冻结状态、预算动作、反事实或可重复 continuation、删失效率指标和停止条件；
  不复用 Issue #419 自然失败项目作为结果后筛选的 treatment 样本。
- 实现 Issue #421 已冻结的下一步 0 Provider 轨迹 benchmark 资格候选；只能使用新的项目族和 identity，先验证
  多步状态、checkpoint clean replay、六维预算守恒和共享预算账本，不实现 controller。

禁止：

- 修改、移动、删除、重新生成、续跑、重跑、replacement 或 backfill 任何历史 experiment identity/evidence；
- 修复后继续 mechanism v2，创建 sequence 13/checkpoint 5 evidence，或把旧结果导入新比较；
- 对不完整 mechanism v2 执行 primary/secondary test 或声称 treatment effect；
- 在新 identity、项目、预算、停止规则和明确授权冻结前读取 credential、调用 Provider、创建 formal attempt 或写 formal experiment evidence。
- 对进展状态 v1 做结果后调参、改切分、改标签或改阈值，或据此直接实现 controller/F0/A1。
- 用 Issue #421 已审计的旧轨迹训练、调阈值或评价动态预算 controller，或把 16 个 composite
  `direct -> Agent` arm 当作 pure direct continuation。
- 在当前 v1 上调用 Jev/通用 LLM、调整 RuleGate、继续阶段 B-D 或实现 controller；当前 evaluation 已暴露且 RuleGate 饱和。
- 把阶段 A 的 100% replay 一致率解释为模型效果、成本收益或语义路由成功。
- 修改、重跑、replacement、backfill Issue #391 v2 的项目、故障、动作、成本、阈值、outcome 或报告；在 #391 identity 下读取 credential、调用 Provider 或实现 controller。
- 重跑、续跑、补齐、替换或覆盖 `cpp-jev-offline-qualification-v1/v4/v5/v6`，或把任一失败 identity 的部分响应导入其他 identity。
- 重跑、续跑、替换或覆盖 `cpp-jev-controller-replay-qualification-v1/v2`，或删除 v1 失败 evidence；后续端到端实验不得复用 v6 或 replay identity。
- 重跑、续跑、替换或覆盖 `cpp-jev-end-to-end-canary-v1` 至 `v7`，或把 qualification/canary 结果解释为正式 treatment effect。
- 重跑、续跑、替换、补齐或覆盖 `cpp-jev-formal-comparison-v1` 至 `v6`，或按正式结果调整阈值、样本、预算和停止规则。
- 重跑、续跑、替换、补齐或覆盖 `cpp-jev-hybrid-workflow-qualification-v1/v2/v3` 与 `cpp-jev-hybrid-workflow-canary-v1`，或修改其 raw evidence。
- 重跑、续跑、替换、补齐或覆盖 `cpp-jev-natural-failure-linux-applicability-v3`，或把 v3 的后验人工标签改写进正式 report/evidence。
- 在独立 identity、自然失败样本、预算、停止规则和 create-once evidence 目录冻结前调用下一阶段 Provider 或写新实验 evidence。
- 重跑、续跑、替换、补齐或覆盖 `cpp-jev-natural-failure-default-path-qualification-v1`，修改其机械 stop 标签，或
  为该 identity 创建 reference/action/Provider 子实验。

## 权威入口

- Mechanism v2 formal manifest：`benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-formal-execution.json`。
- Mechanism v2 冻结 evidence：`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent`。
- Mechanism v2 失败审计：`benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.md`。
- Runtime v3 qualification：`benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md`。
- Stage C v8 审计：`benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md`。
- Issue #419 正式默认路径报告：`benchmarks/reports/cpp-jev-natural-failure-default-path-qualification-v1.md`；结果审计：
  `benchmarks/reports/cpp-jev-natural-failure-default-path-qualification-v1-result-audit.md`；raw evidence：
  `.compile-sessions/benchmark-evidence-jev-natural-failure-default-path-qualification-v1`。
- Issue #421：`https://github.com/WWFXL/Forge-AutoCompiler/issues/421`；审计设计：
  `docs/superpowers/specs/2026-10-12-dynamic-budget-identifiability-audit-design.md`；机器可读结果：
  `benchmarks/reports/cpp-dynamic-budget-identifiability-audit-v1.json`；研究报告：
  `benchmarks/reports/cpp-dynamic-budget-identifiability-audit-v1.md`。
- Issue #423：`https://github.com/WWFXL/Forge-AutoCompiler/issues/423`；资格设计：
  `docs/superpowers/specs/2026-10-12-dynamic-budget-trajectory-benchmark-qualification-design.md`；最终 v4 报告：
  `benchmarks/reports/cpp-dynamic-budget-trajectory-benchmark-qualification-v4.md`；冻结 evidence：
  `.compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v1` 至 `v4`。v4 inventory canonical
  SHA-256 为 `e398003b48a2ded0b745900900481a21b2aa5879f3296ba71c06032f50e55294`。
- Issue #425：`https://github.com/WWFXL/Forge-AutoCompiler/issues/425`；恢复安全设计：
  `docs/superpowers/specs/2026-10-12-symlink-safe-checkpoint-restore-gate-design.md`；工程门禁报告：
  `benchmarks/reports/cpp-symlink-safe-checkpoint-restore-gate-v1.md`。
- 2026-10-06 已按 `search_notes -> read_note` 核对个人知识库论文索引、CXXCrafter 和 CompileAgent 解读；本轮不修改知识库。
- 2026-10-07 已按 `search_notes -> read_note` 核对个人知识库笔记“Forge 毕业论文方向与契约驱动修复设计”；本轮不修改知识库。
- 2026-10-09 已按 `search_notes -> read_note` 核对个人知识库“2025-2026 自动化编译论文索引”和旧方向设计原文；本轮不修改知识库。
- Issue #382：`https://github.com/WWFXL/Forge-AutoCompiler/issues/382`。
- Issue #382 结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/384`；基于 PR #383 的研究审计分支，CI 与评审状态以 PR 为准，不在本阶段合并。
- Issue #385：`https://github.com/WWFXL/Forge-AutoCompiler/issues/385`。
- Issue #385 主动诊断机制审计：`docs/research/2026-10-09-active-diagnosis-mechanism-audit.md`。
- Issue #385 审计 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/386`；基于 `yiwei/382-progress-state-qualification`，依赖 PR #384，CI 与评审状态以 PR 为准，不在本阶段合并。
- Issue #395：`https://github.com/WWFXL/Forge-AutoCompiler/issues/395`。
- Issue #395 formal manifest：`benchmarks/manifests/cpp-jev-offline-qualification-v1.json`。
- Issue #395 冻结 failure evidence：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v1`。
- Issue #395 失败报告：`benchmarks/reports/cpp-jev-offline-qualification-v1.md`。
- Issue #389：`https://github.com/WWFXL/Forge-AutoCompiler/issues/389`。
- Issue #389 分支：`yiwei/389-typed-action-benchmark`，基线 `eb03a873`，实现提交 `87a36c32`；中文 PR #390 已创建并回读，以 `yiwei/387-thesis-research-bar` 为 base，通过 `Closes #389` 关联 Issue。CI 与评审状态以 PR 为准，本阶段不合并。
- Jev 阶段 A JSON 报告 SHA-256：`bdbf2bca0f76c978630d58f618202cc9fb61d968ed287dd74a2f29f5292151d6`。
- RuleGate 可辨识性 JSON 报告 SHA-256：`7ca7e47846ce77001dcf12c99e2615e74e6d2f0803f8ea5e04439db331c5e8c6`。
- Issue #391：`https://github.com/WWFXL/Forge-AutoCompiler/issues/391`；分支 `yiwei/391-semantic-routing-pilot`，结果盲执行 revision `b8b68b1a5457e0097c3d4d1a8213595c73178ece`。
- Jev v2 JSON 报告 SHA-256：`ea2e126e81cfca374900436fa670015b28b3cc3f9d8c83e746ae2c92d2badfed`；Markdown SHA-256：`6220d059fa03e182f7e86c62b2688d91893c1ddbf43b163fd3a9fe8409b95e63`。
- Issue #393：`https://github.com/WWFXL/Forge-AutoCompiler/issues/393`；分支 `yiwei/393-jev-offline-qualification`，基线 `8c36e2ea`。
- Jev 离线资格 candidate manifest canonical SHA-256：`920ee99c3b63218436fdbfdcb86ead0d4bfecb02c833d1652244b9b92a40b583`；后续真实 Provider 执行已通过独立 v4-v6 identities 完成并保留失败链。
- Issue #399：`https://github.com/WWFXL/Forge-AutoCompiler/issues/399`；v4 JSON 报告 SHA-256 `85e62c6fa8b6f4c1d9dc1eabd2808b12ec5cc2d30e5ceb6d16ec9604b6a82909`。
- Issue #400：`https://github.com/WWFXL/Forge-AutoCompiler/issues/400`；v5 JSON 报告 SHA-256 `42512a051c99cbf46279ceb395adc947f9eb27c029e770a7355cd713f8d41327`。
- Issue #401：`https://github.com/WWFXL/Forge-AutoCompiler/issues/401`；v6 manifest canonical SHA-256 `4d17426ecee591584bdfd6d1520c454d3e402d5da894ae54ec7c0841ba067eee`。
- Jev v2-v6 结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/402`；以 `yiwei/395-jev-offline-execution` 为 base，依赖 PR #396，CI 与评审状态以 PR 为准。
- Jev v6 冻结 evidence：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v6`；JSON/Markdown 报告 SHA-256 分别为 `7a9d440acd0dc1b51eea7470563fc263b518fffd428b2e4bd6c3967ab696b2c6`、`cf40eb89063e1757bf78c7d3dca3458afdec2c2f240537e4fab07338483b9bc3`。
- Issue #403：`https://github.com/WWFXL/Forge-AutoCompiler/issues/403`；v1 failure evidence 位于 `.compile-sessions/benchmark-evidence-jev-controller-replay-qualification-v1`，inventory canonical SHA-256 为 `e11cf5aa77587606ec70e5454cbe8b9c2574a34f6c1249660096e5c469863538`。
- Issue #404：`https://github.com/WWFXL/Forge-AutoCompiler/issues/404`；v2 manifest canonical SHA-256 为 `309b02edf34db238e318e2b5f9fbe945692e0d946edb181f76028f1c5bd4ce28`。
- Jev controller replay v2 evidence：`.compile-sessions/benchmark-evidence-jev-controller-replay-qualification-v2`；inventory canonical SHA-256 为 `8a07709058f998b7820677b86754027b17c8e015da2579c41c96783edc80699c`；JSON/Markdown 报告 SHA-256 分别为 `71a8102a5ca89ea194d77d7d853cf413e5c45d3438f4933bdc70e226f27bdfb7`、`ae27029ccd57a346420563fe2d99c057608bdc15a9febcba2b36b99daad5bb4f`。
- Jev controller replay 结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/405`；base 为 `yiwei/401-jev-offline-v6`，依赖 PR #402，通过 `Closes #403` 与 `Closes #404` 关联失败链和最终结论；backend unit 与 frozen benchmark CI 全绿。
- Issue #406：`https://github.com/WWFXL/Forge-AutoCompiler/issues/406`；v7 manifest canonical SHA-256 为 `60355130979a192f256b47411a2c4b2ca51754a72e091d5d7b0753e871f853cb`。
- Jev 端到端 canary v7 evidence：`.compile-sessions/benchmark-evidence-jev-end-to-end-canary-v7`，28 files / 385,384 bytes，inventory canonical SHA-256 `837f0d2702c5e2c959522a51abcd15ea56b079c198a130c2a7454960c9f293d9`；JSON/Markdown 报告 SHA-256 分别为 `2fdbf0d64c3254b4e4dedc39c2f59b525febb0b0ad0d5dd25ed20e2858597ef4`、`13dd8346e7d85844958e4a48d0d3134c8bb9377ed2bce2bddb598144df16080c`。
- Issue #408：`https://github.com/WWFXL/Forge-AutoCompiler/issues/408`；v6 manifest canonical SHA-256 为 `cd5f30686677c6ac2aab1226f44437bbc0ed5ef1a702a45629bef157c35ad414`，正式 release revision 为 `65a051b8bdadbece7fe1bf18fbc6f83e75141a17`。
- Jev 正式比较 v6 evidence：`.compile-sessions/benchmark-evidence-jev-formal-comparison-v6`；72/72 attempt marker 均为 completed，全部 cleanup 且 0 managed resources。JSON/Markdown 报告 SHA-256 分别为 `620e0c823dc00ababc4ba7b283c548a4823e7c7d1147ef72f289f7f940b53c15`、`1fbc08bd5652bda48174520e3051d715e96150c1ade794e1430bbc9b76a77837`。
- Issue #409：`https://github.com/WWFXL/Forge-AutoCompiler/issues/409`；混合链路 canary manifest canonical SHA-256 为 `9abebe01635161cff64220e0e7748a2bb7eef3f7cb9e220c0ecc3c77651866b2`，release revision 为 `71fdc281ce3c082664f118f98ef84546dc9395a3`。
- 混合链路 canary evidence：`.compile-sessions/benchmark-evidence-jev-hybrid-workflow-canary-v1`；3/3 attempt marker completed，10 files / 132,192 bytes，inventory canonical SHA-256 `6b6424f65603bc0d9a1b4c379fa7ad37206cbe6f437bd50395512c8586b4b859`。JSON/Markdown 报告 SHA-256 分别为 `1e6ecc0c464fe8450a5e164f3d4708f0c8bef68310825c7f084011b46cac79d6`、`8c5869a102f0e0dd8c401b99062190900a86cdc92bb0e4b15f21ee3dd5c91bb9`。
- 混合链路结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/410`；base 为 `yiwei/408-jev-formal-comparison`，通过 `Closes #409` 关联 tracking Issue，CI 与评审状态以 PR 为准。
- 进展状态 v1 manifest canonical SHA-256：`9340a10f005a9a90f980ac45356e8c13d00f35a7b095e30a68ccde610944ee6d`。
- 进展状态 v1 JSON 报告 SHA-256：`b4b682d8699bdbcf5e768736e525ac13109675db64971a23c3007dafa2442a4d`。

## 下一项工作

Issue #425 已通过 symlink-safe checkpoint restore 工程门禁，解除 v4 暴露的合法 libtool 相对链接恢复阻塞。下一阶段
为全新的 `dynamic_budget_trajectory_benchmark_qualification_v5` 编写 spec、manifest 和预注册，冻结独立 create-once
evidence root，并让 v5 使用已通过门禁的恢复模块；不得续跑或复制补齐 v1-v4。v5 仍是 0 Provider 跨 CMake/Make/
Autotools 轨迹资格，只有 checkpoint clean continuation、逐决策六维预算、共享预算转移和项目族覆盖全部通过后，才允许
设计 Agent continuation 资格；通过前不读取 credential、不调用 Jev/Agent，也不实现动态预算 controller。
