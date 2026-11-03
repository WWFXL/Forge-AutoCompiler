#!/usr/bin/env python3
"""从独立36次只读分析绘制论文图，不修改原始证据。"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for path in Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc"):
    font_manager.fontManager.addfont(str(path))
plt.rcParams.update(
    {"font.family": "Noto Sans CJK JP", "svg.fonttype": "none", "font.size": 11}
)
METHODS = {
    "no_experience": "A 无经验",
    "source_experience": "B 旧经验\n来源检索",
    "action_experience": "C 短动作\n迁移候选",
}


def plot(analysis, output):
    groups = [analysis["summary"][m] for m in METHODS]
    x = range(3)
    fig, axes = plt.subplots(3, 1, figsize=(8.4, 10.2))
    complete = [g["complete"] for g in groups]
    axes[0].bar(x, complete, color="#4e8e67", label="完整")
    axes[0].bar(
        x,
        [g["observed"] - g["complete"] for g in groups],
        bottom=complete,
        color="#cc8056",
        label="未完整",
    )
    axes[0].bar(
        x,
        [g["unobserved"] for g in groups],
        bottom=[g["observed"] for g in groups],
        color="#dddddd",
        label="未观察",
    )
    axes[0].set(title="(a) 固定36次排期，每组12次", ylabel="运行次数", ylim=(0, 15))
    for i, g in enumerate(groups):
        axes[0].text(i, 12.4, f"{g['complete']}/12", ha="center")
    axes[0].legend(frameon=False, ncol=3, loc="upper center")
    online = [float(g["cost_usd"]) for g in groups]
    prep = [float(g["seed_preparation_cost_usd"]) for g in groups]
    total = [a + b for a, b in zip(online, prep)]
    axes[1].bar(x, online, color="#4b76a8", label="全部在线请求")
    axes[1].bar(
        x, prep, bottom=online, color="#d2bfdf", hatch="//", label="各部署一次库制作"
    )
    axes[1].set(
        title="(b) 在线费用与一次库制作",
        ylabel="估费 / 美元",
        ylim=(0, max(total) * 1.35),
    )
    for i, v in enumerate(total):
        axes[1].text(i, v + max(total) * 0.025, f"{v:.3f}", ha="center")
    axes[1].legend(frameon=False, ncol=2, fontsize=9, loc="upper center")
    minutes = [g["wall_minutes"] for g in groups]
    axes[2].bar(x, minutes, color="#7c8fa6")
    axes[2].set(
        title="(c) 全部在线槽累计时间（含编译与干净重放）",
        ylabel="分钟",
        ylim=(0, max(minutes) * 1.2),
    )
    for i, v in enumerate(minutes):
        axes[2].text(i, v + max(minutes) * 0.025, f"{v:.1f}", ha="center")
    for ax in axes:
        ax.set_xticks(list(x), list(METHODS.values()))
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
    fig.text(
        0.5,
        0.008,
        "B/C库均已制作；部署成本各计一次，本批不重新付费提炼。时间不含库准备。",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output.with_suffix("." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(json.loads(args.analysis.read_text()), args.output)
