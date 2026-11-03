#!/usr/bin/env python3
"""从只读四组分析绘制完成、部署成本与时间；不改变原数据。"""

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
    "source_experience": "B 旧提炼\n来源检索",
    "process_experience": "C 过程提炼\n来源检索",
    "conditioned_experience": "D 过程提炼\n逐条选择",
}


def plot(analysis, output):
    groups = [analysis["summary"][m] for m in METHODS]
    x = range(4)
    fig, axes = plt.subplots(3, 1, figsize=(9, 10.4))
    complete = [g["complete"] for g in groups]
    axes[0].bar(x, complete, color="#4e8e67", label="完整完成")
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
    axes[0].set(title="(a) 固定48次排期，各组12次", ylabel="运行次数", ylim=(0, 15))
    for i, g in enumerate(groups):
        axes[0].text(i, 12.3, f"{g['complete']}/12", ha="center")
    axes[0].legend(frameon=False, ncol=3, fontsize=9, loc="upper center")
    initial = [
        sum(float(r["initial_cost_usd"]) for r in analysis["slots"] if r["method"] == m)
        for m in METHODS
    ]
    recovery = [
        sum(
            float(r["recovery_cost_usd"]) for r in analysis["slots"] if r["method"] == m
        )
        for m in METHODS
    ]
    prep = [float(g["seed_preparation_cost_usd"]) for g in groups]
    online = [a + b for a, b in zip(initial, recovery)]
    total = [a + b for a, b in zip(online, prep)]
    axes[1].bar(x, initial, color="#4b76a8", label="初始规划")
    axes[1].bar(x, recovery, bottom=initial, color="#e2a263", label="异常恢复")
    axes[1].bar(
        x, prep, bottom=online, color="#d2bfdf", hatch="//", label="各部署一次库制作"
    )
    axes[1].set(
        title="(b) 全部已观察请求及一次经验库制作",
        ylabel="估费 / 美元",
        ylim=(0, max(total) * 1.35),
    )
    for i, v in enumerate(total):
        axes[1].text(i, v + max(total) * 0.025, f"{v:.3f}", ha="center")
    axes[1].legend(frameon=False, fontsize=8, ncol=3, loc="upper center")
    minutes = [g["wall_minutes"] for g in groups]
    preparation = [g["seed_preparation_seconds"] / 60 for g in groups]
    all_time = [a + b for a, b in zip(minutes, preparation)]
    axes[2].bar(x, minutes, color="#7c8fa6", label="全部在线槽")
    axes[2].bar(
        x,
        preparation,
        bottom=minutes,
        color="#d2bfdf",
        hatch="//",
        label="一次提炼调用",
    )
    axes[2].set(
        title="(c) 在线槽与一次提炼的累计时间",
        ylabel="分钟",
        ylim=(0, max(all_time) * 1.3),
    )
    for i, v in enumerate(all_time):
        axes[2].text(i, v + max(all_time) * 0.02, f"{v:.1f}", ha="center")
    axes[2].legend(frameon=False, fontsize=9, loc="upper center", ncol=2)
    for ax in axes:
        ax.set_xticks(list(x), list(METHODS.values()))
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
    fig.text(
        0.5,
        0.008,
        "B库制作是既有成本；C/D共用同一提炼，分别显示各自部署成本，不重复算作本轮支出。",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output.with_suffix("." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(json.loads(args.analysis.read_text()), args.output)


if __name__ == "__main__":
    main()
