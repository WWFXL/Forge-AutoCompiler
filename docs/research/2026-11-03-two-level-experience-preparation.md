# 两层经验复用：实现与完整比较设计

Issue #668；2026-11-03。本阶段由用户明确批准四步计划及全部预算。执行者自设共享20美元/准备起12小时，实际起止以新会话授权为准，不复用E39余额。

新增`project_experience.py`实现项目配方和状态目标经验选择。配方从真实完整成功的最终方案抽取dependency/configure/build动作，保留原命令和检查；按当前任务重新装配测试与交付，不调用模型翻译文字经验。源码/归档/镜像/构建系统/产物必须一致；目标变化只在显式试用模式执行并记录，默认不当精确命中。失败仍调用原恢复Agent；完整成功后保存本槽新版配方，不覆盖旧库，也不污染后续比较。

跨项目保持已有24条经验及原条目、来源材料组装、top3来源/12000字节、每任务一次快照；新选择使用经验条件/动作和当前目标及真实失败词项，恢复过滤同阶段。无新增提炼、嵌入模型或相关性模型；英文标识与中文二字词的公开简单打分，不将其称为语义推理算法。引用成功命令、命中经验或生成新版配方均不等于迁移有效或自进化收益。

两个独立身份及前瞻顺序在[协议](../../benchmarks/preregistrations/cpp-build-two-level-experience-v1.md)和同名manifest：24次`cpp-build-project-recipe-reuse-flash-v1`，其中三项目原条件、三项Release→Debug；36次`cpp-build-state-target-retrieval-flash-v1`，无经验/原检索/状态目标检索。源码版本与原作者测试保持；Debug是两方法共同的新任务要求，不是放宽原任务。全部费用、早停及恢复计入，不补槽。

16项相关/相邻检查通过。真实零Provider接线材料保存在`/home/yiwei/.codex/outputs/forge-two-level-experience-preparation-v1`及v2：v1的tinyxml2为Make任务，两例均未触发配置目标变化，因此只说明直接复用可运行，不作为恢复证据。v2使用CMake yaml-cpp核对直接复用与Debug修订恢复。最终实际结果以各目录result.json为准。以上均为工程准备，不计论文模型效果分母。

新会话`/home/yiwei/.codex/outputs/forge-two-level-experience-session-v1`保存授权、冻结种子及项目配方；正式raw分别为`forge-project-recipe-reuse-flash-v1`和`forge-state-target-retrieval-flash-v1`。运行后统一分析，报告同条件/目标变化、初始/恢复费用、完整结果及任务后更新，并更新论文第5/6章。旧E39与v0.5继续有效。
