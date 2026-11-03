#!/usr/bin/env python3
"""从两组独立分析绘图，保留完整分母、恢复费与未观察。"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for path in Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc"):
    font_manager.fontManager.addfont(str(path))
plt.rcParams.update({"font.family": "Noto Sans CJK JP", "svg.fonttype": "none"})

LABELS = {
    "replan": "重新规划",
    "recipe_reuse": "同项目方案复用",
    "no_experience": "无经验",
    "source_retrieval": "原来源检索",
    "state_target_retrieval": "状态目标检索",
}


def plot(value, output):
    methods = list(value["two_level_summary"])
    groups = [value["two_level_summary"][m] for m in methods]
    planned = [value["summary"][m]["planned"] for m in methods]
    x = list(range(len(methods)))
    fig, axes = plt.subplots(3, 1, figsize=(8.7, 9.6))
    complete = [g["complete"] for g in groups]
    observed = [g["observed"] for g in groups]
    axes[0].bar(x, complete, color="#4d8c67", label="完整")
    axes[0].bar(
        x,
        [n - c for n, c in zip(observed, complete)],
        bottom=complete,
        color="#c7825d",
        label="未完整",
    )
    axes[0].bar(
        x,
        [n - o for n, o in zip(planned, observed)],
        bottom=observed,
        color="#d9dee5",
        label="未观察",
    )
    axes[0].set(
        title="(a) 固定排期与完整任务", ylabel="运行次数", ylim=(0, max(planned) * 1.3)
    )
    for i, (c, n) in enumerate(zip(complete, planned)):
        axes[0].text(i, n + 0.18, f"{c}/{n}", ha="center", fontsize=10)
    axes[0].legend(ncol=3, frameon=False, loc="upper center")
    initial = [float(g["initial_cost_usd"]) for g in groups]
    recovery = [float(g["recovery_cost_usd"]) for g in groups]
    total = [a + b for a, b in zip(initial, recovery)]
    axes[1].bar(x, initial, color="#4b78a6", label="初始规划／探索")
    axes[1].bar(x, recovery, bottom=initial, color="#bb8d61", label="全部失败恢复")
    axes[1].set(
        title="(b) 本轮在线模型估费",
        ylabel="美元",
        ylim=(0, max(max(total), 0.001) * 1.3),
    )
    for i, v in enumerate(total):
        axes[1].text(
            i, v + max(max(total), 0.001) * 0.025, f"{v:.4f}", ha="center", fontsize=10
        )
    axes[1].legend(ncol=2, frameon=False, loc="upper center")
    minutes = [g["wall_minutes"] for g in groups]
    axes[2].bar(x, minutes, color="#8295ab")
    axes[2].set(
        title="(c) 全部槽累计耗时（含测试与干净重放）",
        ylabel="分钟",
        ylim=(0, max(max(minutes), 0.1) * 1.22),
    )
    for i, v in enumerate(minutes):
        axes[2].text(
            i, v + max(max(minutes), 0.1) * 0.025, f"{v:.1f}", ha="center", fontsize=10
        )
    for ax in axes:
        ax.set_xticks(x, [LABELS[m] for m in methods])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
    note = (
        "方案复用的历史首次构建费另列；图中不将其视为免费。"
        if "replan" in methods
        else "两检索组复用同24条库；既有制库费0.095129美元另列，不是本轮新增支出。"
    )
    fig.text(
        0.5, 0.008, note + "\n失败早停不能单独解释为效率优势。", ha="center", fontsize=9
    )
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output.with_suffix("." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plot(json.loads(args.analysis.read_text()), args.output)
