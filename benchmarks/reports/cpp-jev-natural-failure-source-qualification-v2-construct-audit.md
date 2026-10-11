# Jev 自然失败 source qualification v2 构造效度审计

日期：2026-10-11。追踪：Issue #413。该文档只读审计已冻结的 build qualification，不修改生成报告、
raw evidence 或项目标签。

## 结论

生成 runner 的机械决定为 `proceed_to_reference_recipe_qualification_v2`：24/24 项完成，17 项被分类为
`stable_natural_failure`，CMake、Make、Autotools 的角色计数均达到预注册门槛。

进入 reference recipe identity 前的源码与严格终点审计发现冻结的 Make calibration 单元不可能达到
reference-eligible 配额。最终决定为：

`stop_natural_failure_evaluation_v2_before_reference_recipe`

不创建 reference recipe、typed action matrix 或 Provider identity。这个决定否定 v2 source contract 的
Linux target applicability 筛选，不评价 Jev 的自然失败路由能力。

## 正式 attempt 事实

- execution revision：`ca2d5380119eaf1dc3a09097273aebef3bea56c3`；
- 24/24 项完成，分类为 17 个稳定失败、6 个初始成功、1 个运行时网络依赖排除；
- 稳定失败角色计数：CMake `1/1/3`、Make `1/1/4`、Autotools `2/1/3`；
- 434 个 evidence 文件，共 736,283 bytes，inventory canonical SHA-256
  `d2c61123506f80dd925f4df20e12bd1c613bb46959ab1ccc401f90d90ea1d658`；
- 生成 JSON/Markdown 报告 SHA-256 分别为
  `f46494bc41f8db7fa0157d32a97ee3379717bf3f574843a76842749a4e485f18` 和
  `1d028d582545afaefcbea065845c775a5e277617dd502ff2b3071129d770ebec`；
- 0 credential、0 Provider、0 model token、0 reference recipe、0 action matrix，24 项 cleanup 全部通过，
  最终 0 受管容器。

## 决定性 Make calibration 单元

该单元冻结了两个项目：

| 项目 | 生成分类 | reference failure 候选 |
| --- | --- | --- |
| `sogou/workflow` | `initial_success` | 否：没有自然失败 checkpoint |
| `felixkratz/sketchybar` | `stable_natural_failure`，build / compile_error | 否：唯一 primary build path 是 macOS 目标 |

`SketchyBar@515046e8a150d6b8767a8a6dd624824eaafa2c8b` 的 README 明确描述 macOS menu bar，根 tree 中
唯一构建入口是 blob `7eb46331573a680aa1b282c53b7e8f3eb4c4fca6` 的 `makefile`。该文件：

- x86 目标固定 `-target x86_64-apple-macos10.13`；
- arm64 目标固定 `-target arm64-apple-macos11`；
- 链接 Carbon、AppKit、QuartzCore、CoreAudio、CoreWLAN、CoreVideo、IOKit 和 Apple 私有 framework；
- 用 `lipo` 合并 Mach-O 目标。

两个 Linux replicate 都在约 0.4 秒处失败，GCC 明确拒绝 Apple `-target` 参数。stdout/stderr SHA-256
分别为 `4232941a...6016` 和 `541c1a97...8261`。这不是安装 Linux 依赖或选择另一个项目 target 可以修复的
失败。

Forge 冻结的严格终点只把 ELF executable/shared/object 或 `ar` static archive 识别为编译产物，见
`backend/packages/harness/deerflow/compile/operations.py` 的 `_classify_compiled_artifact`。即使另行引入
Apple SDK 交叉编译，Mach-O 也不能通过相同终点；放宽 verifier 又会破坏实验可比性。

因此 Make calibration 的 reference-eligible 自然失败上限为 `0`，低于预注册要求 `>=1`。角色不能前移，
项目不能替换，继续审核其他 16 个失败无法改变该结论。

## 说明了什么

1. result-blind GitHub 搜索、根入口、submodule 和网络信号足以产出可执行且稳定的双 replay 数据，但
   “主语言是 C/C++ + 根 Makefile”仍不能保证存在 Linux C/C++ primary target；
2. 只看重复失败阶段和错误类别会把确定性平台不兼容误当成自然构建失败；
3. reference closure 必须在动作矩阵和 Provider 前作为资格条件，不能用稳定失败数量替代；
4. 若继续自然失败路线，需要在角色冻结前加入 Linux target applicability 审计，检查构建文件中的
   target triple、framework、SDK、平台 guard 和产物格式。

本轮不能回答 Jev 是否能处理自然失败，也不能评价 action diversity、RuleGate 难度、自然失败成功率、
Provider 成本或动态预算控制。
