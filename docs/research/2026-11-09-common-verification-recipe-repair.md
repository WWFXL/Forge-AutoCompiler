# 共同验证、依赖配方与结果标签修复

本阶段为工程修复，完成后结束，不开展新的付费模型比较。它解决E52暴露的共同机制缺口，不修改原36次结果，也不把修复收益计入H1/H2。

## 已实现的机制

1. **作者有依据的轻量验证。** 独立`BuildReference.executable_smokes`按精确交付文件名绑定`smoke`步骤、来源及非空输出依据。Workflow实际执行后，复用现有`ExecutableVerificationPolicy`，并将成功记录加入重放验证脚本。验证参考不进入规划或恢复上下文。没有显式参考时沿用现有三参数默认检查，不盲目增加`-V`等参数，也没有项目名称分支。
2. **成功依赖默认保留。** 恢复交接包含成功依赖及命令ID。遗漏不再等于删除，系统在有效方案中保留成功dependency；原容器复用实际成功记录，不因配置变化重复安装。废弃/替换须用`discard_dependencies`写明原ID及理由，未知ID、隐式覆盖和改名重复执行被拒绝。配置后缀仍失效，配方按实际命令先后选择有效成功记录，不累加所有历史命令。干净重放继续检查依赖是否真的可省略。
3. **分层标签。** `final_verification_passed`分列最终submit验证，`clean_replay`只取本次实际attempt；前置阻断无attempt为`not_started`，未进入后检查为`unobserved`。新增`reproducible_delivery_completed`同时要求主产物、交付、最终验证、实际重放、源码及清理成功。`main_build_task_completed`保留主构建范围，不能代替可复现交付；完整作者测试仍为`not_required`、旧`full_completed`为null。

详细行为和边界见[执行契约](../compile_workflow_execution.md)。新共同提示明确区分基础镜像已有依赖与本轮临时安装；未来实验必须固定这一共同版本，不把它当作旧H0/H1/H2的同一提示版本。

## 四条针对性真实构建

工程身份`cpp-build-common-verification-recipe-repair-v2`，固定源码和镜像取自E52公开任务归档。独立新容器各执行一次，原容器和重放使用相同源码归档、不可变镜像及2并行。沿用main-build-v1的主要产物、源码、精确交付与重放检查；不增加完整作者测试。

| 工程路径 | 原容器主产物/交付 | 最终验证 | 实际重放 | 用时秒 |
| --- | --- | --- | --- | --- |
| fse，作者`/artifacts/fse -V` | 通过 | 通过 | 通过 | 15.27 |
| fse，受控错误参数`--version` | 通过 | 拒绝 | 未启动 | 7.71 |
| libsigcplusplus，修订遗漏安装步骤，由系统保留 | 通过 | 通过 | 通过 | 139.18 |
| libsigcplusplus，显式废弃仍必需的安装步骤 | 通过 | 拒绝 | 执行失败 | 88.03 |

fse的作者依据是`programs/commandline.c:73,165`；实际`-V`命令与输出通过原容器和新容器的验证，错误参数未被放行。

两条libsigcplusplus先执行原成功安装与配置方案，在默认文档构建处真实失败，再使用原H2末次关闭文档的方案。正例没有重新加入安装步骤，系统保留`install-mm-common`及其成功ID；原容器只安装一次，最终build recipe保留安装，新容器成功重建。负例仅额外显式声明废弃安装，原容器仍可生成主库，但新容器缺`mm-common-prepare`，exit 127、`recipe_execution_failed`，按原标准拒绝。

四条源码及cleanup均通过，合计约250.19秒。Provider调用、模型Token及费用均为0；两条恢复各使用一次零Token脚本响应，meter记录的2次模型接口响应不是真实Provider请求。它们只支持上述执行语义与错误拒绝，不估计模型能力、自然项目成功率、自动Harness更新效果或任意Shell兼容性。

## 验证与保留的失败

95项相关行为回归通过，包含真实本机Shell/编译、依赖保留/替换及结果分层；标准产品测试范围2828通过、46跳过。修改文件Ruff和格式检查通过。编译及重放容器的实际清理核验见原件`verification.json`。

先前工程v1保留：首条fse在原容器显式smoke已成功，但接线未把该成功记录同时传入verification recipe，既有submit正确拒绝，重放未启动。随后补齐接线及回归断言，在独立v2运行上述四条，不续跑或覆盖v1。最初局部测试的夹具注册/本机交付路径及错误文本断言问题已校正；最终95相关与标准产品范围均通过，不以早期测试输出充当完成。

## 证据与论文用途

- [可重复执行的工程驱动](../../scripts/forge_common_verification_repair.py)：只读历史动作，输出目录必须不存在，无Provider构造或凭据读取。
- 原件：`/home/yiwei/.codex/outputs/forge-common-verification-recipe-repair-2026-11-09-v2`；`scope.json`固定边界及运行代码哈希，`cases.json`固定四路径，`source-snapshot/`保存代码，`summary.json`/`completed.json`/`verification.json`和每会话命令、配方、日志及实际attempt保存观察。
- 原件inventory canonical SHA-256：`e152b617714c16ef1071dff381e64717a5530edf180572bbb64f9e658a80d968`。编译/重放共8个容器的16项名称/ID实际不存在（含v1）。
- 先前失败：同级`forge-common-verification-recipe-repair-2026-11-09-v1`，原始结果和日志保留。
- E52仍按其[原报告](2026-11-09-offline-harness-round2-results.md)和原分母解释；当前修改不重算旧冻结结果，不更新论文数值或冒称v0.10已重新导出。
- 论文用途：第4章说明执行与重建配方的区分，第6章解释前置验证阻断与真实重放失败；作为共同工程修复材料，不增加效果样本分母。

本阶段结束。默认仍保留基础H0；后续研究可固定这套共同底座，再研究恢复Harness的轨迹驱动更新。本轮不启动下一次优化或比较。跟踪[Issue707](https://github.com/WWFXL/Forge-AutoCompiler/issues/707)，代码发布与检查终态以关联PR和GitHub为准。
