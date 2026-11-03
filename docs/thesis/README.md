# Forge 硕士论文阶段初稿

日期：2026-11-03；版本：v0.5；本轮跟踪：[Issue #664](https://github.com/WWFXL/Forge-AutoCompiler/issues/664)；历史完整比较：[Issue #660](https://github.com/WWFXL/Forge-AutoCompiler/issues/660)、[PR #661](https://github.com/WWFXL/Forge-AutoCompiler/pull/661)。

暂定题目：**面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究**。

本目录保存按章维护的论文真源。第3/4章基础方法、第5章经验实现及第6章独立比较分别对应证据，不把新增组件写进旧实验条件。当前是可供审阅的阶段正文；学校正式模板、封面、声明和最终文献格式尚待补齐。

## 从哪里阅读

- [完整目录](CONTENTS.md)与`chapters/`：正文修改真源，目录由导出程序生成。
- [系统图](figures/system-overview.png)：实线为在线构建控制，紫色虚线为已实现的任务后经验与上下文数据流；虚线不表示效果已经证明，也不表示所有研究入口均已进入Web产品。
- [正文—证据映射](EVIDENCE_MAP.md)：定位每张实验表的版本、分母与权威报告。
- [本轮短动作报告](../research/2026-11-03-transfer-action-experience-results.md)：独立36次；初始探索节约、恢复／部署成本取舍及空材料分层。
- [前版过程经验报告](../research/2026-11-03-conditioned-experience-results.md)：独立48次、过程提炼/逐条选择、全部成本及采用/越界反例。
- [前版经验报告](../research/2026-11-03-state-experience-comparison-results.md)：独立36次经验复用及12次更新，分母和旧失败保持。
- [待补清单](TODO.md)与[文献BibTeX](references.bib)：后续写作与正式著录入口。

v0.5新增E39完整36次、表6-19/20与图6-5，保留E38中止及旧实验。新派生Word/PDF/HTML/Markdown在`/home/yiwei/.codex/outputs/forge-thesis-transfer-action-2026-11-03/`，前缀`Forge-硕士论文阶段初稿-v0.5`；实际核对66页PDF、33表6图及新增31/52–55页；正文约3.65万汉字。导出统计与文件指纹见该目录build-summary.json及export-verification.json。

v0.4.1导出保留在forge-thesis-task-action-2026-11-03，62页PDF、31表5图。

历史v0.4派生Word/PDF/HTML/Markdown位置为`/home/yiwei/.codex/outputs/forge-thesis-conditioned-experience-2026-11-03/`，文件名前缀`Forge-硕士论文阶段初稿-v0.4`。已实检61页PDF、31表5图，正文约3.27万汉字；文件指纹与新增页阅读核验见该目录build-summary.json及export-verification.json。v0.3保留在forge-thesis-experience-2026-11-03，v0.1/v0.2亦保留。各格式是同一正文的阅读副本，修改应回到本目录。

## 当前完成范围

| 部分 | v0.5内容 |
|---|---|
| 摘要、绪论、相关研究 | 按实际完成范围组织问题、贡献与文献定位，不称通用机制首创 |
| 第3章 | 任务、阶段、目标、观测、验证条件与新系统数据流 |
| 第4章 | 状态选择、直接动作、方案修订、后缀重执行及工具局部恢复 |
| 第5章 | 实际经验schema、来源绑定、阶段/词项检索、上下文注入、任务后追加、过程证据、逐条必要信号选择、来源实例／迁移候选分离及对应算法 |
| 第6章 | E30/E33系统结果、E01/E02/E04组件、E34恢复接口、E35/E36/E37/E39独立经验比较、更新、分层验证及实际采用/越界反例 |
| 第7章 | 根据对应版本的结果总结，区分方法可运行与效果成立 |
| 附录 | 版本、主要运行参数、六项目源码版本及实验身份 |
| 学校格式与个人信息 | 尚待正式模板及用户提供，不推断填写 |

## 编辑与生成

```bash
python3 docs/thesis/tools/build_draft.py \
  --version v0.5 --date 2026-11-03 \
  --output-dir /home/yiwei/.codex/outputs/forge-thesis-transfer-action-2026-11-03 \
  --deps-dir /home/yiwei/.codex/outputs/forge-thesis-draft-2026-11-02/.doc-libs
```

Word/HTML使用外部目录的`python-docx`、`Markdown`依赖；有系统安装可省略`--deps-dir`。PDF由LibreOffice从Word转换。图表由render_system.py、render_experience_selection.py及scripts/plot_experience_results.py、scripts/plot_conditioned_experience.py、scripts/plot_transfer_action_results.py生成PNG/SVG/PDF。文稿导出本身0 Provider，不代表本轮真实实验没有支出；无需为导出运行产品全测或编译容器。

## 证据与能力边界

基础系统继续使用E30/E33，配置增量用E01/E02解释；E34工具局部恢复和E35/E36/E37经验比较各自独立。经验实验运行release bb08aaaa与公开准备提交6745dc5a的完整Git tree相同，源revision映射与最终发布以报告和PR为准。写作revision不替换实际实验revision。

E35无经验/原轨迹/结构化完整12/12、12/12、8/12，结构化不支持总体优势，保留inja局部节约和底座误判等失败原因。提炼请求RichLab gpt-6-astra、响应gpt-5.6已按用户确认披露，不能证明后端为Astra或更强。固定经验与任务后更新分别评价，不能由检索命中推出自进化。全部负向结果和未观察保留；私人知识库通过MCP同步，不复制Vault或注入实验Agent。

E37四组完整11/12、12/12、12/12、11/12，旧经验在线费用低6.1%、时间接近，但含制库更贵。新过程和逐条选择未整体占优，保留局部节约、当前状态触发经验引用及误删原有文档Makefile的反例。旧实验不回写，导出文稿不改变运行release。

E38已完成13条短动作提炼，但36比较槽均未观察；固定六项目初始选择全部为空。见[本轮报告](../research/2026-11-03-action-experience-stopped-and-repair.md)，不将调度修复或空经验比较写成方法效果。

E39的C/B初始读取少33.3%、初始费低9.8%，恢复几乎抵消节约，总费仅低0.34%、时间更高，含制库更贵。部分有利波动出现在空材料任务；两个A未完整涉及过程与共同阶段分类限制，不写成经验普遍提高编译能力。运行revision0d78f589保持，不以写作HEAD替代。
