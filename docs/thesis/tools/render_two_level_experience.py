#!/usr/bin/env python3
"""绘制两层经验的使用边界；图中不预设任何效果结论。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

for path in Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc"):
    font_manager.fontManager.addfont(str(path))
plt.rcParams.update({"font.family": "Noto Sans CJK JP", "svg.fonttype": "none"})


def main():
    fig, ax = plt.subplots(figsize=(11.8, 8.1))
    ax.set(xlim=(0, 12), ylim=(0, 8.3))
    ax.axis("off")
    blue, green, orange, purple = "#416b9b", "#367653", "#a9652e", "#8664a5"

    def box(x, y, w, h, title, body, color=blue):
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=.03",
                facecolor="#fafbfd",
                edgecolor=color,
                linewidth=1.3,
            )
        )
        ax.text(
            x + w / 2,
            y + h * 0.69,
            title,
            ha="center",
            va="center",
            fontsize=12,
            color=color,
            weight="bold",
        )
        ax.text(
            x + w / 2,
            y + h * 0.29,
            body,
            ha="center",
            va="center",
            fontsize=9.5,
            color="#334359",
            linespacing=1.5,
        )

    def arrow(points, label=None, pos=None, color=blue, dashed=False):
        style = "--" if dashed else "-"
        for a, b in zip(points[:-2], points[1:-1]):
            ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=1.2, linestyle=style)
        ax.add_patch(
            FancyArrowPatch(
                points[-2],
                points[-1],
                arrowstyle="-|>",
                mutation_scale=13,
                color=color,
                lw=1.2,
                linestyle=style,
            )
        )
        if label:
            ax.text(
                *pos,
                label,
                ha="center",
                va="center",
                fontsize=9.5,
                color=color,
                bbox=dict(facecolor="white", edgecolor="none", pad=1),
            )

    ax.text(
        0.15,
        8.02,
        "两层经验：复用同项目方案，参考跨项目建议",
        fontsize=18,
        weight="bold",
        color="#24394f",
    )
    box(
        4.1,
        6.8,
        3.8,
        0.85,
        "当前任务与候选匹配",
        "固定源码、镜像、产物；核对当前验证目标",
    )
    box(
        0.35,
        4.9,
        4.7,
        1.15,
        "第一层：已验证项目方案",
        "匹配 → 复用依赖／配置／编译命令\n当前测试与交付重新装配；跳过初始模型规划",
        green,
    )
    box(
        6.95,
        4.9,
        4.7,
        1.15,
        "第二层：跨项目条件经验",
        "未命中 → 同构建系统、不同来源族\n依据当前目标选择一次；供规划Agent核对",
        purple,
    )
    box(
        3.75,
        3.2,
        4.5,
        1.05,
        "统一Workflow与真实状态",
        "执行当前方案，保存退出码、日志与目标检查",
    )
    box(
        0.35,
        1.25,
        4.7,
        1.1,
        "当前任务完整验证",
        "原测试、源码保持、精确交付、干净重放\n全部满足且清理成功 → 保存新版项目方案",
        green,
    )
    box(
        6.95,
        1.25,
        4.7,
        1.1,
        "原恢复Agent",
        "失败 → 按实际阶段／交接选择一次经验\n返回修订方案；重执行受影响后缀",
        orange,
    )
    arrow(
        [(4.1, 7.2), (2.7, 7.2), (2.7, 6.05)],
        "精确匹配／显式目标变化试用",
        (2.65, 6.55),
        green,
    )
    arrow(
        [(7.9, 7.2), (9.3, 7.2), (9.3, 6.05)], "没有可用项目方案", (9.3, 6.55), purple
    )
    arrow([(2.7, 4.9), (2.7, 4.55), (5, 4.55), (5, 4.25)], color=green)
    arrow([(9.3, 4.9), (9.3, 4.55), (7, 4.55), (7, 4.25)], color=purple)
    arrow(
        [(4.65, 3.2), (4.65, 2.85), (2.7, 2.85), (2.7, 2.35)],
        "方案步骤完成",
        (2.75, 2.85),
        green,
    )
    arrow(
        [(7.3, 3.2), (7.3, 2.85), (9.3, 2.85), (9.3, 2.35)],
        "实际失败／目标不满足",
        (9.3, 2.85),
        orange,
    )
    arrow([(6.95, 1.8), (6, 1.8), (6, 3.2)], color=orange)
    arrow(
        [(0.35, 1.8), (0.1, 1.8), (0.1, 5.45), (0.35, 5.45)], color=green, dashed=True
    )
    ax.text(
        6,
        0.53,
        "跨项目经验提供建议，不能改变当前验收；目标变化试用不等于精确命中。",
        fontsize=10,
        ha="center",
        color="#44566a",
    )
    ax.text(
        6,
        0.17,
        "正式比较中，新版方案只存本槽，不加入后续重复；不能由追加数量推断持续学习收益。",
        fontsize=9.5,
        ha="center",
        color="#657184",
    )
    fig.tight_layout(pad=0.4)
    output = Path(__file__).resolve().parents[1] / "figures/two-level-experience"
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output.with_suffix("." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
