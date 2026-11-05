#!/usr/bin/env python3
"""绘制当前主构建范围的两层入口与有界状态动作流程；不表示新增效果。"""

from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update(
    {"font.family": "Noto Sans CJK JP", "svg.fonttype": "none", "pdf.fonttype": 42}
)
fig, ax = plt.subplots(figsize=(11.4, 8.2))
ax.set(xlim=(0, 12), ylim=(0, 9))
ax.axis("off")
blue, green, orange, ink = "#eaf1f8", "#eaf4ed", "#fff1e1", "#203c56"


def box(x, y, w, h, text, color=blue):
    ax.add_patch(
        FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0.08,rounding_size=0.12",
            facecolor=color,
            edgecolor=ink,
            linewidth=1.1,
        )
    )
    ax.text(
        x, y, text, ha="center", va="center", fontsize=10, color=ink, linespacing=1.6
    )


def arrow(start, end, label=None, rad=0):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.1,
            color=ink,
            connectionstyle=f"arc3,rad={rad}",
        )
    )
    if label:
        ax.text(
            (start[0] + end[0]) / 2,
            (start[1] + end[1]) / 2 + 0.13,
            label,
            ha="center",
            fontsize=9,
            color=ink,
            bbox=dict(facecolor="white", edgecolor="none", pad=1),
        )


box(6, 8.35, 7.2, 0.65, "简洁任务：固定源码与环境，构建主要程序或库")
box(
    2.4,
    7.05,
    3.45,
    0.9,
    "同项目成功方案精确匹配\n全部公开任务字段，忽略运行标签",
    green,
)
box(8.55, 7.05, 3.9, 0.9, "没有精确方案 → 初始规划 Agent\n作者材料 + 一次条件经验检索")
arrow((4.5, 8.0), (2.4, 7.56))
arrow((7.5, 8.0), (8.55, 7.56))
box(
    6,
    5.75,
    5.4,
    0.8,
    "Workflow 执行依赖／配置／编译动作\n记录命令、工作目录、退出结果和日志",
)
arrow((2.4, 6.52), (4.8, 6.22), "命中：省去模型规划")
arrow((8.55, 6.52), (7.3, 6.22))
box(
    6,
    4.45,
    6.4,
    0.8,
    "状态观察：阶段目的 + 实际反馈 + 配置／主产物\n阶段成功、前置缺失、执行失败、证据不足",
)
arrow((6, 5.28), (6, 4.92))
box(1.6, 2.92, 2.7, 0.92, "阶段满足\n继续下一步", green)
box(5.15, 2.92, 3.25, 0.92, "异常且有明确证据\n选择有限局部动作", orange)
box(9.45, 2.92, 3.65, 0.92, "无适用动作／仍未解决\n恢复 Agent 返回修订方案", orange)
arrow((3.7, 4.0), (1.6, 3.45))
arrow((5.55, 4.0), (5.15, 3.45))
arrow((8.3, 4.0), (9.45, 3.45))


def routed(points):
    ax.plot(*zip(*points[:-1]), color=ink, linewidth=1.1)
    arrow(points[-2], points[-1])


routed([(1.6, 3.45), (0.12, 3.8), (0.12, 5.75), (3.2, 5.75)])
routed([(5.15, 2.38), (5.15, 2.08), (11.55, 2.08), (11.55, 5.75), (8.8, 5.75)])
routed([(9.45, 2.38), (9.45, 2.08), (11.55, 2.08), (11.55, 5.75), (8.8, 5.75)])
ax.text(
    7.2,
    2.15,
    "修订后实际重执行变化后缀",
    fontsize=8.5,
    color=ink,
    ha="center",
    bbox=dict(facecolor="white", edgecolor="none", pad=2),
)
box(
    6,
    1.25,
    8.9,
    1.02,
    "主要产物独立确认 → 精确交付 → 干净构建重放 → 源码与清理\n主任务完成与交付／重放分列；完整作者测试不默认要求",
    green,
)
arrow((1.6, 2.38), (1.6, 1.82))
ax.text(
    1.55,
    2.12,
    "全计划完成",
    fontsize=8.5,
    color=ink,
    ha="right",
    bbox=dict(facecolor="white", edgecolor="none", pad=2),
)
ax.text(
    6,
    0.3,
    "仅当主任务、交付、重放、源码和清理成功才保存新方案；本批不回流后续重复",
    ha="center",
    fontsize=9,
    color=ink,
)
fig.tight_layout()
out = Path(__file__).resolve().parents[1] / "figures"
out.mkdir(exist_ok=True)
for ext in ("png", "svg", "pdf"):
    fig.savefig(
        out / f"main-build-workflow.{ext}",
        dpi=210,
        bbox_inches="tight",
        facecolor="white",
    )
    if ext == "svg":
        path = out / "main-build-workflow.svg"
        path.write_text(
            "\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n"
        )
plt.close(fig)
