# 四项目参考任务资格 v2：三系统严格闭合

Issue #484；身份 `cpp-build-plan-source-qualification-v2`。决定为 `proceed_to_bounded_plan_vs_tool_agent_canary_design`：四个预定项目全部通过完整任务测试、精确产物、干净重建和清理，原始普通源码/测试逐文件哈希未变，封存及独立只读审计通过。0Provider/0模型tokens。这是后续比较的可执行性资格，不是模型能力或方法效果。

| 项目 | 固定测试入口 | 固定交付 | 结果 |
| --- | --- | --- | --- |
| miniz / CMake | 开启BUILD_TESTS，CTest实际注册并执行catch_tests，100%通过 | libminiz.a | verified/completed |
| md4c / CMake | 上游Python入口：调用、全部文本suite、病理输入；保留上游允许失败 | 静态链接md2html | verified/completed |
| pigz / Make | 上游make test，保留条件compress分支及原Shell语义，不称完整tests目标 | pigz | verified/completed |
| libite / Autotools | make check全部21项，21 PASS、0 SKIP/FAIL/ERROR | libite.a | verified/completed |

各项均执行重放测试和精确产物比较；所有Session cleanup成功。本阶段使用事先固定的人工参考方案，不能当规划Agent结果。四个项目已成为开发暴露，不能再称最终未见holdout。

唯一修订是libite bootstrap去掉autoreconf的`-s`，以同样工具辅助文件的副本替代系统绝对链接。v1执行成功但封存审计失败的目录及报告仍只读；未放宽审计器或测试，未把v1回填成v2。

身份定义：`benchmarks/manifests/cpp-build-plan-source-qualification-v2.json`，SHA-256 `4d6bd00bc926dc45be1f32c6007f86bcd6ec4a500c4ebf8d0b9e9e507061c2d6`，对应预注册同名Markdown。原始 `/home/yiwei/.codex/outputs/forge-source-qualification-v2/`，1743 files / 46,440,633 bytes；inventory canonical SHA-256 `8c5a6b46a83715fec922b8287acaa282b6225f367508715aaed87bb48d328bae`。外部独立审计 `forge-continuous-research-2026-10-19/source-qualification-v2-audit.json`，valid=true。边界/完整性回归3 passed，backend/ruff.toml下check和format通过。

下一问题：在相同输入、模型、资源和严格终点下，初始完整方案+Workflow与逐步工具型构建Agent是否都能闭合，模型调用/资源差异来自哪里。先做有限开发canary及强基线接线，不据四个小项目估计总体成功率，不把普通顺序执行或DAG缓存本身称为通用首创。
