# Forge 硕士论文阶段初稿

日期：2026-11-17；版本：**v0.12**；[Issue #813](https://github.com/WWFXL/Forge-AutoCompiler/issues/813)。

题目：**面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究**。

本目录按章维护论文真源，沿用七章框架。v0.12经用户批准纳入E58全18项目/36次领域Harness更新比较，并用上下文同材料回放和libffi开发案例解释作用机制。论证沿“状态感知执行→真实轨迹诊断→工具、经验及上下文更新→全流程成本评价”推进，保留E57及其他历史实验原分母。上下文修复为E58两组共同底座，以机制证据说明，不混入组间费用归因。

## 论证与最终系统方案（2026-11-12）

[核心论证—证据对应表](ARGUMENT_BLUEPRINT.md)与[最终系统组件清单](FINAL_SYSTEM_DESIGN.md)明确两项研究工作、主文/附录取舍和后续评价配置。P0＋初始工具约束＋R2已是E57 B组实测配置；精确复用作为可选扩展。原方案反映E57时点；本轮追加E58证据及最新已评价组合，历史选型与产品默认分别保留，不新增实验。

方案Word：`/home/yiwei/.codex/outputs/forge-thesis-argument-system-2026-11-12/Forge-论文核心论证与最终系统方案-v1.0.docx`。

方案已实际导出并以python-docx重新打开：49段、4表，关键结果与本地链接检查通过；SHA-256 `aaf6737dd56f5f74b0f1c9a47cfda7be67460bafa61183dbdebcf044f44bd9ab`。未做逐页渲染，本文件是审阅方案，不是新的论文正文版本。

## 最新阅读入口

**仅导出Word**：`/home/yiwei/.codex/outputs/forge-thesis-harness-update-word-2026-11-17/Forge-硕士论文阶段初稿-v0.12.docx`。

- [七章目录](CONTENTS.md)与`chapters/`是修改真源。
- [正文—证据映射](EVIDENCE_MAP.md)对应实验身份、分母和取数报告。
- [修订与交付记录](../research/2026-11-17-thesis-harness-update-revision.md)记录本次审读和实际导出检查。
- [待补清单](TODO.md)列学校格式、个人信息及导师审阅事项。

## 当前内容

| 部分 | 内容 |
|---|---|
| 摘要、第1章 | 问题、两项研究工作、系统/组件/Harness比较的关键发现 |
| 第2章 | 自动化构建、Agent、Harness与经验相关工作 |
| 第3章 | 任务、阶段与方案表示，简洁主构建入口与分层结果 |
| 第4章 | 真实状态观察、有限直接动作、Agent恢复、受影响后缀重执行 |
| 第5章 | 经验提炼/复用、离线提示更新、工具执行约束及分别比较 |
| 第6章 | 系统比较、状态与恢复消融、经验实验；E51/E52提示更新及E57工具/P4比较，E58依赖/经验组合、libffi与容量机制，表6-1至41 |
| 第7章 | 研究结论、局限与后续问题 |
| 附录 | 参数、提示/工具及固定项目版本，附录I为E57、J新增E58 |

E58两组主构建均17/18、交付均14/18；更新组总费低19.9%、累计时间低13.6%，初始费增加而恢复费下降53.3%。上下文与libffi机制详见第5章5.3.3/5.3.4及第6章6.5.16—6.5.18。

E57三组完成10/12、11/12、10/12。工具约束组比旧行为少19请求、全批费低14.9%，节约集中难例；P4在共同完成10项中8项低费，但总费比约束基线高39.7%。混合结果与全部失败保留，未借入文自动更换默认策略。

## 编辑与导出

```bash
python3 docs/thesis/tools/build_draft.py \
  --version v0.12 --date 2026-11-17 \
  --output-dir /home/yiwei/.codex/outputs/forge-thesis-harness-update-word-2026-11-17 \
  --deps-dir /home/yiwei/.codex/outputs/forge-thesis-draft-2026-11-02/.doc-libs
```

导出器从分章真源生成目录，将图片直接嵌入Word，并保存内部统计JSON；不生成PDF、HTML或Markdown阅读副本。正文修改后重新导出，不调用Provider、不重跑实验。学校模板、作者信息和正式著录仍待完成。

## 历史版本

历史输出保持原样：v0.10在`forge-thesis-offline-harness-round2-2026-11-09`，v0.9在`forge-thesis-offline-harness-results-2026-11-09`，v0.8在`forge-thesis-offline-harness-2026-11-09`，v0.7在`forge-thesis-main-build-2026-11-05`，均位于`/home/yiwei/.codex/outputs/`。旧多格式副本不再作为最新版交付。
