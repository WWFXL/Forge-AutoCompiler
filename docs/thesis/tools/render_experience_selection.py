#!/usr/bin/env python3
"""绘制失败过程提炼与逐条选择方法，不读取实验结果。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

for path in Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc"):
    font_manager.fontManager.addfont(str(path))
plt.rcParams.update({"font.family": "Noto Sans CJK JP", "svg.fonttype": "none"})
fig, ax = plt.subplots(figsize=(12, 6.2))
fig.subplots_adjust(left=0.02, right=0.98, bottom=0.04, top=0.98)
ax.set(xlim=(0, 12), ylim=(0, 6.2))
ax.axis("off")


def box(x, y, w, h, title, body, color="#426da5"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.04,rounding_size=.1",
            facecolor="#f5f7fa",
            edgecolor=color,
            lw=1.3,
        )
    )
    ax.text(
        x + w / 2,
        y + h * 0.71,
        title,
        ha="center",
        va="center",
        weight="bold",
        fontsize=11,
        color=color,
    )
    ax.text(
        x + w / 2,
        y + h * 0.29,
        body,
        ha="center",
        va="center",
        fontsize=10,
        linespacing=1.5,
    )


def arrow(a, b, color="#426da5"):
    ax.add_patch(
        FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=13, lw=1.3, color=color)
    )


ax.text(
    0.15,
    5.85,
    "离线：只使用允许的历史来源",
    fontsize=13,
    weight="bold",
    color="#3d516b",
)
box(
    0.15, 4.15, 3.2, 1.25, "真实过程材料", "命令 / 方案 / 失败交接\n实际修订 / 验证范围"
)
box(
    4.15,
    4.15,
    3.35,
    1.25,
    "过程经验提炼",
    "失败尝试 → 反馈 → 已观察修订\n局部有效 / 无效 / 未执行假设",
)
box(
    8.3,
    4.15,
    3.35,
    1.25,
    "带来源的固定经验库",
    "条件 / 阶段 / 动作 / 结果 / 证据\n必要文件、声明词、错误片段",
)
arrow((3.4, 4.78), (4.1, 4.78))
arrow((7.55, 4.78), (8.25, 4.78))
ax.text(
    0.15, 3.5, "在线：仅使用当前可观察信息", fontsize=13, weight="bold", color="#3d516b"
)
box(
    0.15,
    1.7,
    3.2,
    1.25,
    "当前任务状态与归档声明",
    "初始任务或真实失败handoff\n不读取未来结果",
)
box(
    4.15,
    1.7,
    3.35,
    1.25,
    "逐条适用信号检查",
    "同系统 / 异项目族 / 阶段匹配\n文件、声明及当前错误确认",
)
box(8.3, 1.7, 3.35, 1.25, "排序与有界装配", "最多3条 / 12000字节\n未确认可返回空经验")
arrow((3.4, 2.33), (4.1, 2.33))
arrow((7.55, 2.33), (8.25, 2.33))
arrow((9.98, 4.1), (5.83, 3.02), "#8c6bb2")
box(
    4.15,
    0.05,
    7.5,
    1.05,
    "原规划 / 恢复Agent与Workflow",
    "自然语言条件仍须核对；实际执行和完整验证决定任务结果",
    "#368058",
)
arrow((9.98, 1.65), (9.98, 1.15), "#368058")
ax.text(
    0.15,
    0.5,
    "信号确认 ≠ 充分适用\n检索命中 ≠ 实际采用\n实际成功 ≠ 单步因果",
    fontsize=10,
    color="#665b51",
    linespacing=1.7,
)
root = Path(__file__).resolve().parents[1] / "figures"
for suffix in ("png", "svg", "pdf"):
    fig.savefig(root / f"experience-selection.{suffix}", dpi=180, bbox_inches="tight")
plt.close(fig)
