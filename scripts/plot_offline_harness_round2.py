#!/usr/bin/env python3
"""绘制十二项目固定分母的完成、全部在线费用及时间，不推断显著性。"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "Noto Sans CJK JP", "svg.fonttype": "none", "pdf.fonttype": 42})
METHODS = ("H0", "H1", "H2")
COLORS = ("#4c78a8", "#e5a04c", "#459e83")


def main(source, output):
    value = json.loads(source.read_text())
    arms = [value["arms"][method] for method in METHODS]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    for i, arm in enumerate(arms):
        axes[0].bar(i, arm["final_verification_passed"], color=COLORS[i])
        axes[0].bar(i, arm["observed"] - arm["final_verification_passed"], bottom=arm["final_verification_passed"], color="#d6a1a1")
        axes[0].bar(i, arm["unobserved"], bottom=arm["observed"], color="#dce1e5")
        axes[0].text(i, arm["planned"] + 0.3, f"{arm['final_verification_passed']}/{arm['planned']}", ha="center")
    axes[0].set(ylabel="最终验证通过 / 计划分母", ylim=(0, 14.5))
    for ax, field, label, scale in ((axes[1], "estimated_cost_usd", "在线模型估费（美元）", 1), (axes[2], "total_wall_seconds", "累计全流程（分钟）", 1 / 60)):
        values = [float(arm[field]) * scale for arm in arms]
        ax.bar(range(3), values, color=COLORS)
        for i, number in enumerate(values):
            ax.text(i, number + max(values) * 0.025, f"{number:.4f}" if scale == 1 else f"{number:.2f}", ha="center", fontsize=9)
        ax.set(ylabel=label, ylim=(0, max(values) * 1.24))
    for ax in axes:
        ax.set_xticks(range(3), ("H0 共同提示", "H1 原策略", "H2 近期更新"), rotation=12)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.17)
        ax.set_axisbelow(True)
    fig.text(0.5, 0.012, "12项目各一次，主产物均12/12；费用含失败/恢复，提案另列；灰红色为最终验证未通过", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    output.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        path = output / f"offline-harness-round2.{ext}"
        fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
        if ext == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.summary, args.output)
