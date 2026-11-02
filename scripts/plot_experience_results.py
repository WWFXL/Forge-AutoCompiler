#!/usr/bin/env python3
"""用正式经验实验的派生分析绘图；不调用模型，不修改原始数据。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for font_path in Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc"):
    font_manager.fontManager.addfont(str(font_path))
plt.rcParams.update(
    {"font.family": "Noto Sans CJK JP", "svg.fonttype": "none", "font.size": 11}
)
LABELS = {
    "no_experience": "无经验",
    "raw_trajectory": "原轨迹片段",
    "structured_experience": "结构化经验",
    "fixed_bank": "固定经验库",
    "updating_bank": "更新经验库",
}


def plot(analysis: dict, output: Path, seed_cost: float, seed_seconds: float):
    methods = [name for name in LABELS if name in analysis["summary"]]
    groups = [analysis["summary"][m] for m in methods]
    labels = [LABELS[m] for m in methods]
    x = range(len(methods))
    # 纵排保证缩入论文正文宽度后仍能读清轴标签。
    fig, axes = plt.subplots(3, 1, figsize=(8.4, 9.8))
    is_main = "no_experience" in methods
    ax = axes[0]
    completed = [g["complete"] for g in groups]
    incomplete = [g["observed"] - g["complete"] for g in groups]
    unobserved = [g["unobserved"] for g in groups]
    ax.bar(x, completed, color="#4e8e67", label="完整完成")
    ax.bar(x, incomplete, bottom=completed, color="#cc8056", label="未完整")
    ax.bar(
        x,
        unobserved,
        bottom=[g["observed"] for g in groups],
        color="#dddddd",
        label="未观察",
    )
    for i, g in enumerate(groups):
        ax.text(i, g["planned"] + 0.15, f"{g['complete']}/{g['planned']}", ha="center")
    ax.set(
        title="(a) 固定分母的完整完成",
        ylabel="运行次数",
        ylim=(0, max(g["planned"] for g in groups) * 1.2),
    )
    ax.legend(frameon=False, fontsize=9, loc="upper center", ncol=3)

    ax = axes[1]
    initial = [
        sum(float(r["initial_cost_usd"]) for r in analysis["slots"] if r["method"] == m)
        for m in methods
    ]
    recovery = [
        sum(
            float(r["recovery_cost_usd"]) for r in analysis["slots"] if r["method"] == m
        )
        for m in methods
    ]
    updates = [
        float(analysis.get("update_cost_usd", 0)) if m == "updating_bank" else 0
        for m in methods
    ]
    preparation = [seed_cost if m == "structured_experience" else 0 for m in methods]
    ax.bar(x, initial, color="#4b76a8", label="初始规划")
    ax.bar(x, recovery, bottom=initial, color="#e2a263", label="失败恢复")
    online = [a + b for a, b in zip(initial, recovery)]
    if is_main:
        ax.bar(
            x,
            preparation,
            bottom=online,
            color="#d2bfdf",
            hatch="//",
            label="新种子提炼",
        )
    else:
        ax.bar(x, updates, bottom=online, color="#9373af", label="任务后更新")
    totals = [a + b + c for a, b, c in zip(online, updates, preparation)]
    for i, value in enumerate(totals):
        ax.text(
            i, value + max(totals) * 0.025, f"{value:.3f}", ha="center", fontsize=10
        )
    ax.set(title="(b) 全部已观察请求估费", ylabel="美元", ylim=(0, max(totals) * 1.42))
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    ax = axes[2]
    minutes = [g["wall_minutes"] for g in groups]
    extraction_minutes = [
        seed_seconds / 60
        if m == "structured_experience"
        else analysis.get("update_request_wall_seconds", 0) / 60
        if m == "updating_bank"
        else 0
        for m in methods
    ]
    all_minutes = [a + b for a, b in zip(minutes, extraction_minutes)]
    ax.bar(x, minutes, color="#7c8fa6", label="在线槽运行")
    ax.bar(
        x,
        extraction_minutes,
        bottom=minutes,
        color="#d2bfdf",
        hatch="//",
        label="经验提炼调用",
    )
    for i, value in enumerate(all_minutes):
        ax.text(i, value + max(all_minutes) * 0.025, f"{value:.1f}", ha="center")
    ax.set(
        title="(c) 在线运行与提炼调用累计耗时",
        ylabel="分钟",
        ylim=(0, max(all_minutes) * 1.22),
    )
    ax.legend(frameon=False, fontsize=9)
    for ax in axes:
        ax.set_xticks(list(x), labels)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    footnote = (
        "结构化组加入一次种子提炼费与调用耗时；首次停止请求另计。\n共同固定任务与验收、含失败开销；早停不代表同等完成下的加速。"
        if is_main
        else "两组共享种子准备；更新组计入全部任务后提炼费与调用耗时（包括末任务）。\n失败早停不能作为同等完成下的加速。"
    )
    fig.text(0.5, 0.015, footnote, ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0.055, 1, 1), h_pad=1.6)
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg", "pdf"):
        metadata = {"Date": None} if suffix == "svg" else None
        target = output.with_suffix("." + suffix)
        fig.savefig(target, dpi=180, metadata=metadata)
        if suffix == "svg":
            target.write_text(
                "\n".join(line.rstrip() for line in target.read_text().splitlines())
                + "\n"
            )
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed-cost", type=float, default=0.095129)
    parser.add_argument("--seed-seconds", type=float, default=0)
    args = parser.parse_args()
    plot(
        json.loads(args.analysis.read_text()),
        args.output,
        args.seed_cost,
        args.seed_seconds,
    )


if __name__ == "__main__":
    main()
