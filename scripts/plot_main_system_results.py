#!/usr/bin/env python3
"""从固定分母分析绘制主任务、在线费用与总耗时；不计算未经支持的显著性。"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

METHODS = ("forge", "forge_experience", "strong_tool_agent")
LABELS = ("基础 Forge", "经验 Forge", "强工具 Agent")
COLORS = ("#4c78a8", "#459e83", "#e5a04c")
STRATA = (
    ("all", "全负载"),
    ("exact_reuse", "精确方案复用"),
    ("no_recipe", "没有精确方案"),
)
plt.rcParams.update(
    {"font.family": "Noto Sans CJK JP", "svg.fonttype": "none", "pdf.fonttype": 42}
)


def main(source, output):
    value = json.loads(source.read_text())
    fig, axes = plt.subplots(3, 3, figsize=(12, 9))
    for j, (key, title) in enumerate(STRATA):
        groups = [value["summary"][key][method] for method in METHODS]
        for k, g in enumerate(groups):
            ax = axes[0, j]
            ax.bar(k, g["main_task_completed"], color=COLORS[k])
            ax.bar(
                k,
                g["observed"] - g["main_task_completed"],
                bottom=g["main_task_completed"],
                color="#d6a1a1",
            )
            ax.bar(k, g["unobserved"], bottom=g["observed"], color="#dce1e5")
            ax.text(
                k,
                g["planned"] + 0.25,
                f"{g['main_task_completed']}/{g['planned']}",
                ha="center",
                fontsize=9,
            )
        axes[0, j].set(
            title=title,
            ylim=(0, max(g["planned"] for g in groups) * 1.25),
            ylabel="主任务完成 / 固定分母" if j == 0 else "",
        )
        for i, (field, ylabel, scale) in enumerate(
            (
                ("estimated_cost_usd", "在线模型估费（美元）", 1),
                ("total_wall_seconds", "累计全流程（分钟）", 1 / 60),
            ),
            start=1,
        ):
            vals = [float(g[field]) * scale for g in groups]
            axes[i, j].bar(range(3), vals, color=COLORS)
            axes[i, j].set(
                ylabel=ylabel if j == 0 else "", ylim=(0, max(max(vals), 0.001) * 1.25)
            )
            for k, v in enumerate(vals):
                axes[i, j].text(
                    k,
                    v + max(max(vals), 0.001) * 0.035,
                    f"{v:.4f}" if i == 1 else f"{v:.2f}",
                    ha="center",
                    fontsize=8,
                )
        for i in range(3):
            axes[i, j].set_xticks(range(3), LABELS, rotation=16, fontsize=8)
            axes[i, j].spines[["top", "right"]].set_visible(False)
            axes[i, j].grid(axis="y", alpha=0.17)
            axes[i, j].set_axisbelow(True)
    fig.text(
        0.5,
        0.012,
        "main-build-v1；作者完整测试不要求；费用含失败与恢复，历史获取投入另列；重复不等于独立项目",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    output.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(
            output / f"main-system-comparison.{ext}",
            dpi=220,
            bbox_inches="tight",
            facecolor="white",
        )
        if ext == "svg":
            path = output / "main-system-comparison.svg"
            path.write_text(
                "\n".join(line.rstrip() for line in path.read_text().splitlines())
                + "\n"
            )
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("summary", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    main(args.summary, args.output)
