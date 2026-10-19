# 两项参考配方独立修复资格结果

Issue #508 / PR #512，身份`cpp-build-reference-repair-qualification-v1`，release70740367，manifest SHA `e839a2b65c3149c438d1518d5655d5312279bfd3b60080c3485d1d45c6603e71`、64组件。0Provider/0凭据，仅对#493中两个已明确的问题做新身份参考资格；旧#493失败不回填，libffi未解决不替补。不称新holdout或模型结果。

## 固定修复与结果

| 项目 | 唯一配方变化 | 固定完整测试 | 严格终点 |
| --- | --- | --- | --- |
| libpng | stage改为`cp build/libpng.a /artifacts/libpng.a` | 37/37，PNG_TESTS/SHARED/STATIC均ON | qualified、Session completed、精确交付/源码不变/replay/cleanup均过 |
| libzip | 原configure追加`-DBUILD_DOC=OFF` | 199/199，REGRESS/BZIP2/LZMA/ZSTD/OPENSSL均ON | qualified、Session completed、精确交付/源码不变/replay/cleanup均过 |

BUILD_DOC是原源码CMake明确定义的选项，文档不是任务交付/回归目标；关闭文档生成避免重生成110个原man HTML，不关闭或替换任何原测试，也不豁免源码内容变化。两任务各运行一次、900秒方案/600秒replay、2CPU；均在UTC22:15新项目准入前开始，阶段UTC22:45截止，未并行其他构建实验。

## 封存与核验

raw `/home/yiwei/.codex/outputs/forge-reference-repair-qualification-v1/`，6166普通文件/16链接/173305266 bytes，inventory `9eb4c2d336766e6c66aff742f771dcd93686aece0eac70d5e40b619cd2ba0e3c`。本轮外部目录下reference-repair-v1-inventory-audit.json与reference-repair-v1-outcome-audit.json均valid=true、issues/errors为空，独立核验typed inventory、原始源码/归档、精确交付、固定完整测试、replay/cleanup和0残留容器。

4项针对性测试、Ruff/format、完整父封存只读validate通过；结果提交后仍须最终head三项实际CI全SUCCESS才合并。manifest明确记录相对旧父已存在的三个Agent时限文件变化；本阶段不调用相应Agent路径，run_reference本身字节不变，unchanged函数AST也与父相同，不能称所有导入文件与旧父完全一致。整个阶段0Provider/0Token，未增加共享费用。

## 结论与下一步

两项新人工参考资格全部闭合，说明原失败有具体、可运行且不降低固定任务标准的配方修正。它们可为未来独立比较提供资格候选，但本次不加入#493/#502/#504任何分母，不把7/10事后改成9/10，也不证明模型会自行选择这些修复。

当前主线继续完成接管材料工程修复与真实成本/恢复状态审计，之后按项目族/时间隔离冻结新的评估协议。源码合同仍较强，通常功能正确但修改原文件或不产生确定字节的项目依旧可能不在当前严格任务适用域内；本轮不放宽标准。
