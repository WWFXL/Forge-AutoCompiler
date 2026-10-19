# 构建方案与恢复 Agent 真实试运行完成报告

日期：2026-10-19（北京时间）。跟踪：[Issue #469](https://github.com/WWFXL/Forge-AutoCompiler/issues/469)。类型：工程修复与探索性真实试运行。

## 结果

**cJSON正常构建与受控错误target恢复两条路径均完成。** 成功attempt使用真实DeepSeek Pro thinking生成完整初始方案和恢复修订，Workflow实际执行；两路径分别通过19项CTest、精确交付、独立空工作区clean replay、产物类型/大小/SHA-256比较以及cleanup，Session最终均为`completed`。

这完成了本轮最小真实接入试运行，不是正式方法效果实验。此前失败全部保留，成功并非首次尝试；不能把两个开发路径称为两个独立项目或自然失败样本。

## 实际执行链路

成功轮使用只读收集器提供源码材料包：完整根CMakeLists.txt、tests/CMakeLists.txt、fuzzing/CMakeLists.txt，以及README前80行，附完整文件哈希、行号和截断标记。材料包22780字节，不含预制方案、历史成功轨迹或个人知识库。模型输出完整`PlanProposal`，没有直接Shell权限。成功轮没有执行交互式源码读取工具，也没有使用任意终端型Compiler Agent；它验证的是材料包驱动的规划/修订与Workflow链路。

初始方案由模型生成，实际执行：

```sh
cmake -S /workspace/repo -B /workspace/repo/build
cmake --build /workspace/repo/build -j2
ctest --test-dir build --output-on-failure
cp /workspace/repo/build/libcjson.so.1.7.19 /artifacts/libcjson.so.1.7.19
```

正常路径没有交接，4条执行命令完成。受控路径在独立新Session中复用该初始方案，将build替换为不存在的`forge_trial_missing_target`，真实退出码为2。规则状态机根据命令失败暂停并产生交接；模型读取当前完整方案、源码材料和真实日志尾部，返回revision 2，Workflow保留已成功configure并执行修订后的build及后续步骤。修订后的build为默认目标构建，失败命令保留在审计轨迹中，未进入成功重放配方。

| 路径 | Session | 执行命令 | 交接/模型修订 | 原始CTest | 干净重放 | 清理/终态 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 正常 | `9335770708c5` | 4，全部成功 | 0 | 19/19 | 构建及19/19测试通过 | completed |
| 受控恢复 | `4211ebc9925f` | 5，含保留的1次失败 | 1 | 19/19 | 构建及19/19测试通过 | completed |

这两个会话分别交付唯一的`libcjson.so.1.7.19`，50256 bytes；原始构建与重放均为共享库，SHA-256均为`66aea1ae75dd1b7bc196f435f98a4b2b8eabaf1bd6c8bc1282bd4ca13c61286f`。cleanup后再次核对交付未变；独立审计确认编译和重放容器均已删除。

固定来源为`DaveGamble/cJSON@c859b25da02955fef659d658b8f324b5cde87be3`，source tar SHA-256为`26da701f2cb689e042361a4bd8904595f2fa41409812e781fc8759ed54a0f734`，镜像为`sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`，2 CPU。

## 全部尝试与工程更正

| 身份/attempt | 真实请求 | 已知Token | 已知保守估算费用/USD | 结果 |
| --- | ---: | ---: | ---: | --- |
| trial-v1 | 1 | 未知 | 未知 | 首请求400，未构建 |
| trial-v2 | 1 | 1710 | 0.00326832 | 源码工具路径契约错误，未构建 |
| repair attempt-001 | 6 | 68812 | 0.10876008 | 工具探索累积上下文触限，未构建 |
| repair attempt-002 | 1 | 17447 | 0.04465692 | 默认high思考消耗输出上限，结构化参数截断，未构建 |
| repair attempt-003 | 2 | 23291 | 0.03693492 | 两路径均verified并completed |

用户在v2停止后明确要求继续修复直到真实运行完成。在这一授权下建立独立修复campaign，每次失败先封存，再修复并创建新attempt；不是偷偷重跑旧identity或挑选成功覆盖失败。SDK重试始终为0。

更正依次为：明确相对读取路径并提供可纠正工具错误；用有界源码材料包避免探索不断扩充上下文；保持同一模型及thinking开启，将官方支持的`reasoning_effort`从默认high改为low，保留8192输出上限，明确`required_output`是日志字面文本、诊断路径相对workdir。成功轮是low配置，不能与先前high配置合并形成模型能力或收益比较。没有放宽固定测试、交付或clean replay要求。

成功attempt为20946 input、2345 output、23291 total tokens，2次请求分别用于初始规划与恢复修订。全阶段共尝试**11次请求**，其中10次有完整响应，已知总计93549 input、17711 output、**111260 tokens**，按冻结峰时价格保守估算**$0.19362024**。v1的1次未知请求继续按50000 tokens/$0.198预留；估算加预留为**$0.39162024**，低于$2上限，Token加预留161260，低于200000设计上界。预留不是实际费用，不能宣称累计实际账单已完整核实。

attempt-003将单响应上界由50000收紧为25000，准入阈值为37031；既往用量、未知预留、准入及响应上界合计仍200000。代码、协议、授权和实际准入预算均保存在对应attempt，不回改先前预算。

## 核验与证据

- 最新相关回归：**219 passed, 2 skipped**；新runner真实Docker脚本化接线门禁此前**10 passed**（含1项Docker正/受控恢复夹具）。Ruff check/format、Git diff检查通过。脚本化测试不是实际模型能力数据。
- 独立只读审计`valid=true`：逐文件inventory、运行代码快照、授权绑定、请求生命周期/usage/估算、固定smoke、错误target实际失败、修订、失败命令排除、原始及重放测试、产物哈希、cleanup与零匹配容器全部闭合。v1/v2冻结证据未变。
- 所有repair原始attempt位于`/home/yiwei/.codex/outputs/forge-build-plan-agent-repair-v1/`，成功轮为`attempt-003/`。该轮封存2527 files / 28353696 bytes，inventory canonical SHA-256为`44099409b665f7275275d8600d6bfa5ae539971ecacc7526e554617648f02903`。
- 外部审计、可重读的审计脚本、授权上下文及控制台日志位于`/home/yiwei/.codex/outputs/forge-build-plan-agent-repair-2026-10-19/`；入口为`completion-audit.json`、`audit-completion.py`。不往已封存attempt追加分析。
- 协议见`benchmarks/preregistrations/cpp-build-plan-agent-repair-v1.md`；三次设计分别绑定`cpp-build-plan-agent-repair-v1.json`、`cpp-build-plan-agent-repair-v1-attempt-002.json`、`cpp-build-plan-agent-repair-v1-attempt-003.json`。成功设计SHA-256为`d5e34a7487ec8afc1c5496d3949e5eafd3033bf2431eee61be54b776928da873`。
- 当前为本地未提交实现，继承#468工作；没有推送、PR、合并或知识库修改。历史#463/#465/#467均未重开。

## 结论边界与下一步

已支持：该已见CMake开发项目上的“初始模型方案—规则执行—失败交接—模型修订—严格验收与可复现交付”能够端到端闭合。当前选择器仍是规则状态机；本轮没有可学习选择器对照、项目族隔离、重复试验、自然依赖故障或工程成本收益比较。

不能从这里得出跨项目/跨构建系统泛化、自然错误恢复成功率、低思考强度更优、成本下降或论文两个创新点成立。模型文字理由也不能替代证据：初始理由称19个unity测试，源码实际为18个unity测试加1个cJSON_test；本报告以固定CTest的19/19和源码为准。

本轮已结束，不再追加模型请求。下一研究阶段应保持这条最小链路，先做少量Make/Autotools及真实依赖/配置故障的独立走读，观察哪些状态需要Agent、哪些预制动作失效，再据此设计公平基线与选择器比较；不直接扩大正式效果实验或宣称创新已获证实。
