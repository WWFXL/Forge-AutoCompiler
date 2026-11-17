# 工具错误反馈与方案输出修复

## 问题与修复

本轮是E59之后的共同工程修复（Issue #821），不新增正式实验或模型效果分母。

libass的`inspect_build_environment(kind="pkgconfig")`违反工具参数枚举，LangChain ToolNode返回纯文本错误。旧`PlanningContext.observe`直接按JSON解码，先于下一次模型调用崩溃。现在观察器允许纯文本、非对象JSON和显式错误结果，原始ToolMessage及调用ID继续交给Agent；错误不写成成功读取，不进入依赖证据记忆，也不计为新证据。规划和恢复共用该处理。

dsvpn和libtasn1的四份真实非法方案输出均已只读摘录。旧纠正上下文会重新序列化整段坏参数，产生多层转义；现在保留原始响应文件，发给Agent的纠正内容只包括JSON语法位置或Pydantic字段错误，不复制输入值。要求按当前SimpleBuildActions schema重新提交完整对象，正确转义命令，不接续残片。仍只允许一次结构纠正，执行约束纠正仍独立有界；不猜括号、不补命令、不执行未验证方案。

## 验证

- 使用E59封存source-snapshot的观察器及原始libass工具文本，旧实现重现JSONDecodeError；新实现无异常且未增加证据。
- 通过真实LangChain Agent图，受控模型先提交非法kind，再收到原始参数错误、改用合法查询，最后提交完整方案；非法查询未执行实际容器命令，合法查询执行一次。
- 四份真实坏JSON分别收到简短语法反馈，后续脚本完整方案通过；恢复入口同样完成结构纠正和修订装配。连续两份坏输出仍停止，不发第三次请求。字段校验反馈包含错误字段而不回显无效输入。
- 针对性检查与共同构建、恢复诊断、证据记忆回归合计123项通过；Ruff与格式检查通过。原始正式运行只读，未改E59结果或论文。

零Provider回放证明系统能继续处理错误和传递纠正信息。后续有效方案由脚本提供，不能据此认定Flash自主输出成功率提高，也没有证明libtasn1的gnulib版本选择已解决。本轮未改构建执行动作，因此不重复项目资格构建。

## 证据与复现

- 真实失败摘录：`benchmarks/fixtures/e59-output-errors.json`，含来源路径和源文件SHA-256。
- 封存/修复观察器比较：`benchmarks/analyses/tool-output-repair-2026-11-17/replay.py`及`replay.json`。
- 图回放：`backend/tests/test_tool_output_feedback.py`，沿用现有脚本模型与计量器；不读取凭据、不连接Provider。
- 原始数据：`/home/yiwei/.codex/outputs/forge-harness-update-repaired-comparison-flash-2026-11-17-v1`。

在仓库根目录运行：

```bash
PYTHONPATH=backend/packages/harness:scripts backend/.venv/bin/python benchmarks/analyses/tool-output-repair-2026-11-17/replay.py
PYTHONPATH=backend/packages/harness:scripts backend/.venv/bin/python -m pytest -q backend/tests/test_tool_output_feedback.py backend/tests/test_simple_planning.py backend/tests/test_planning_environment.py
```

E59旧`derive.py`包含“旧缺陷应重现”的断言，适用于原运行版本；修复后如需重新派生旧分析，应检出原版本或使用其source-snapshot，不用当前修复代码覆盖历史派生文件。新的前后比较单独存放。

下一步可以在新实验身份下观察真实模型的工具纠正与方案交付；不续用已完成36槽的旧付费授权。E59仍为17/18与16/18，结果待用户审核。
