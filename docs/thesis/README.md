# Forge 硕士论文阶段初稿

日期：2026-11-03；版本：v0.3；本轮跟踪：[Issue #658](https://github.com/WWFXL/Forge-AutoCompiler/issues/658)、[PR #659](https://github.com/WWFXL/Forge-AutoCompiler/pull/659)。

暂定题目：**面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究**。

本目录保存按章维护的论文真源。第3/4章基础方法、第5章经验实现及第6章独立比较分别对应证据，不把新增组件写进旧实验条件。当前是可供审阅的阶段正文；学校正式模板、封面、声明和最终文献格式尚待补齐。

## 从哪里阅读

- [完整目录](CONTENTS.md)与`chapters/`：正文修改真源，目录由导出程序生成。
- [系统图](figures/system-overview.png)：实线为在线构建控制，紫色虚线为已实现的任务后经验与上下文数据流；虚线不表示效果已经证明，也不表示所有研究入口均已进入Web产品。
- [正文—证据映射](EVIDENCE_MAP.md)：定位每张实验表的版本、分母与权威报告。
- [本轮经验报告](../research/2026-11-03-state-experience-comparison-results.md)：完整主比较、独立更新、费用、失败及原始指针。
- [待补清单](TODO.md)与[文献BibTeX](references.bib)：后续写作与正式著录入口。

v0.3派生Word/PDF/HTML/Markdown位置为`/home/yiwei/.codex/outputs/forge-thesis-experience-2026-11-03/`，文件名前缀`Forge-硕士论文阶段初稿-v0.3`。已实检52页PDF、25表3图，正文源稿约2.79万汉字；导出摘要与文件指纹见该目录的`build-summary.json`及`export-verification.json`。v0.2保留在`forge-thesis-local-recovery-2026-11-02/`，v0.1及其旧提交也保留。各格式都是同一正文的阅读副本，修改应回到本目录。

## 当前完成范围

| 部分 | v0.3内容 |
|---|---|
| 摘要、绪论、相关研究 | 按实际完成范围组织问题、贡献与文献定位，不称通用机制首创 |
| 第3章 | 任务、阶段、目标、观测、验证条件与新系统数据流 |
| 第4章 | 状态选择、直接动作、方案修订、后缀重执行及工具局部恢复 |
| 第5章 | 实际经验schema、来源绑定、阶段/词项检索、上下文注入、任务后追加及两个算法 |
| 第6章 | E30/E33系统结果、E01/E02/E04组件、E34恢复接口、E35/E36经验比较与独立更新、分层验证及正负案例 |
| 第7章 | 根据对应版本的结果总结，区分方法可运行与效果成立 |
| 附录 | 版本、主要运行参数、六项目源码版本及实验身份 |
| 学校格式与个人信息 | 尚待正式模板及用户提供，不推断填写 |

## 编辑与生成

```bash
python3 docs/thesis/tools/build_draft.py \
  --version v0.3 --date 2026-11-03 \
  --output-dir /home/yiwei/.codex/outputs/forge-thesis-experience-2026-11-03 \
  --deps-dir /home/yiwei/.codex/outputs/forge-thesis-draft-2026-11-02/.doc-libs
```

Word/HTML使用外部目录的`python-docx`、`Markdown`依赖；有系统安装可省略`--deps-dir`。PDF由LibreOffice从Word转换。图表由`render_system.py`和`scripts/plot_experience_results.py`生成PNG/SVG/PDF。文稿导出本身0 Provider，不代表本轮真实实验没有支出；无需为导出运行产品全测或编译容器。

## 证据与能力边界

基础系统继续使用E30/E33，配置增量用E01/E02解释；E34工具局部恢复和E35/E36经验比较各自独立。经验实验运行release bb08aaaa与公开准备提交6745dc5a的完整Git tree相同，源revision映射与最终发布以报告和PR为准。写作revision不替换实际实验revision。

E35无经验/原轨迹/结构化完整12/12、12/12、8/12，结构化不支持总体优势，保留inja局部节约和底座误判等失败原因。提炼请求RichLab gpt-6-astra、响应gpt-5.6已按用户确认披露，不能证明后端为Astra或更强。固定经验与任务后更新分别评价，不能由检索命中推出自进化。全部负向结果和未观察保留；私人知识库通过MCP同步，不复制Vault或注入实验Agent。
