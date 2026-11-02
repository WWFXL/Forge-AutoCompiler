#!/usr/bin/env python3
"""生成论文系统图；实线为在线控制，紫色虚线为经验数据流。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

for font_path in Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc"):
    font_manager.fontManager.addfont(str(font_path))
plt.rcParams.update({"font.family": "Noto Sans CJK JP", "svg.fonttype": "none"})
ROOT = Path(__file__).resolve().parents[1] / "figures"
BLUE, GREEN, ORANGE, PURPLE = "#426da5", "#368058", "#b86b29", "#8c6bb2"
fig, ax = plt.subplots(figsize=(16, 11.8))
fig.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.98)
ax.set(xlim=(0, 16), ylim=(0, 11.8))
ax.axis("off")


def box(x, y, width, height, title, body, color=BLUE, fill="#edf3fc", dashed=False):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.14",
            facecolor=fill,
            edgecolor=color,
            linewidth=1.3,
            linestyle=(0, (5, 4)) if dashed else "-",
        )
    )
    ax.text(
        x + width / 2,
        y + height * 0.68,
        title,
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color=color,
    )
    ax.text(
        x + width / 2,
        y + height * 0.30,
        body,
        ha="center",
        va="center",
        fontsize=10.4,
        color=color,
        linespacing=1.5,
    )


def arrow(points, color=BLUE, dashed=False, label=None, at=None):
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot(
            [a[0], b[0]],
            [a[1], b[1]],
            color=color,
            lw=1.2,
            linestyle=(0, (5, 4)) if dashed else "-",
        )
    ax.add_patch(
        FancyArrowPatch(
            points[-2],
            points[-1],
            arrowstyle="-|>",
            mutation_scale=12,
            lw=1.2,
            color=color,
            linestyle=(0, (5, 4)) if dashed else "-",
        )
    )
    if label:
        ax.text(
            *at,
            label,
            fontsize=9.1,
            color=color,
            ha="center",
            va="center",
            bbox=dict(facecolor="white", edgecolor="none", pad=1.5),
        )


ax.text(
    0.3,
    11.4,
    "Forge：状态感知构建与经验辅助规划／恢复",
    fontsize=21,
    color="#23384f",
    weight="bold",
)
ax.text(
    0.3,
    10.95,
    "实线：在线构建控制　　紫色虚线：已接入研究入口的经验数据流；效果由独立实验评价",
    fontsize=11,
    color="#42536a",
)
ax.add_patch(
    FancyBboxPatch(
        (0.1, 1.65),
        10.75,
        8.75,
        boxstyle="round,pad=.03,rounding_size=.15",
        facecolor="#fbfcfe",
        edgecolor="#d6e0ed",
        lw=1.2,
    )
)
ax.add_patch(
    FancyBboxPatch(
        (11.35, 1.65),
        4.3,
        8.75,
        boxstyle="round,pad=.03,rounding_size=.15",
        facecolor="#fcf9ff",
        edgecolor=PURPLE,
        lw=1.2,
        linestyle=(0, (5, 4)),
    )
)
ax.text(
    0.45,
    10.05,
    "A　单次任务：状态感知执行与方案式恢复",
    fontsize=13,
    color=BLUE,
    weight="bold",
)
ax.text(
    13.5,
    10.05,
    "B　跨任务经验改进",
    fontsize=13,
    color=PURPLE,
    weight="bold",
    ha="center",
)

box(0.55, 8.6, 3.05, 0.95, "任务输入", "仓库版本 · 环境 · 构建与测试目标")
box(4.2, 8.6, 3.25, 0.95, "模型规划 ①", "只读分析 → 依赖／配置／编译指令")
box(8.05, 8.6, 2.5, 0.95, "装配完整方案", "加入固定测试与交付步骤")
box(0.55, 6.7, 3.05, 1.05, "Workflow执行器", "执行当前方案中的就绪步骤")
box(4.2, 6.7, 3.25, 1.05, "状态观测", "退出码／日志／阶段记录／配置缓存")
box(8.05, 6.7, 2.5, 1.05, "动作选择器", "结合任务目标与实际观测")
box(
    0.55,
    4.5,
    3.05,
    1.15,
    "完整任务验证",
    "原测试 · 源码保持 · 精确交付\n同镜像干净重放",
)
box(0.7, 2.95, 2.8, 0.95, "完整完成", "验证通过并完成清理", GREEN, "#edf7f0")
box(
    4.7,
    4.7,
    3.2,
    1.15,
    "直接配置修订",
    "显式BOOL偏离且满足条件；不调模型",
    GREEN,
    "#edf7f0",
)
box(
    8.15, 2.95, 2.5, 1.3, "恢复Agent ②", "读取实际证据\n返回修订方案", ORANGE, "#fff4e9"
)
box(
    3.7,
    1.95,
    4.35,
    1.15,
    "方案修订与后缀重执行",
    "保留未变成功前缀；从首个变化位置重做",
)
arrow([(3.6, 9.08), (4.2, 9.08)])
arrow([(7.45, 9.08), (8.05, 9.08)])
arrow([(9.3, 8.6), (9.3, 8.15), (2.08, 8.15), (2.08, 7.75)])
arrow([(3.6, 7.23), (4.2, 7.23)])
arrow([(7.45, 7.23), (8.05, 7.23)])
arrow(
    [(9.3, 7.75), (9.3, 7.98), (2.08, 7.98), (2.08, 7.75)],
    label="当前步骤成功且目标满足／无适用配置目标 → 推进下一步",
    at=(5.6, 7.98),
)
arrow(
    [(8.65, 6.7), (8.65, 6.2), (6.3, 6.2), (6.3, 5.85)],
    GREEN,
    label="有充分依据",
    at=(6.75, 6.38),
)
arrow(
    [(10.05, 6.7), (10.3, 6.7), (10.3, 4.5), (9.4, 4.5), (9.4, 4.25)],
    ORANGE,
    label="失败／未知\n或超出范围",
    at=(10.05, 5.45),
)
arrow([(2.08, 6.7), (2.08, 5.65)], label="方案全部步骤完成", at=(2.85, 6.2))
arrow([(2.08, 4.5), (2.08, 3.9)], GREEN)
arrow(
    [(3.6, 5.05), (4.15, 5.05), (4.15, 3.58), (8.15, 3.58)],
    ORANGE,
    label="验证未通过且可恢复",
    at=(6.0, 3.78),
)
arrow([(6.3, 4.7), (6.3, 4.05), (5.88, 4.05), (5.88, 3.1)], GREEN)
arrow([(9.4, 2.95), (9.4, 2.5), (8.05, 2.5)], ORANGE)
arrow([(3.7, 2.52), (0.3, 2.52), (0.3, 7.23), (0.55, 7.23)])
ax.text(
    5.5,
    1.79,
    "资源不足或不可恢复 → 停止并保留实际结果",
    fontsize=9.3,
    color="#728196",
    ha="center",
)

box(
    11.65,
    7.72,
    3.7,
    1.25,
    "经验输入",
    "构建轨迹＋分层验证结果\n保留成功／失败与未观察范围",
    PURPLE,
    "#f5effb",
    True,
)
box(
    11.65,
    5.95,
    3.7,
    1.18,
    "离线提炼与来源校验",
    "条件 · 状态 · 动作 · 结果 · 证据\n引用实际命令，不升级验证标签",
    PURPLE,
    "#f5effb",
    True,
)
box(
    11.65,
    4.2,
    3.7,
    1.18,
    "结构化经验库",
    "有效动作／无效尝试／待验证线索\n更新比较：任务后追加，服务后续任务",
    PURPLE,
    "#f5effb",
    True,
)
box(
    11.65,
    2.3,
    3.7,
    1.3,
    "状态关联检索与适用判断",
    "排除同族及不同构建系统\n词项与阶段排序 → 规划／恢复上下文",
    PURPLE,
    "#f5effb",
    True,
)
arrow([(13.5, 7.72), (13.5, 7.13)], PURPLE, True)
arrow([(13.5, 5.95), (13.5, 5.38)], PURPLE, True)
arrow([(13.5, 4.2), (13.5, 3.6)], PURPLE, True)
arrow(
    [(10.55, 7.23), (11.05, 7.23), (11.05, 8.35), (11.65, 8.35)],
    PURPLE,
    True,
    label="任务结束后",
    at=(11.05, 7.92),
)
arrow(
    [(11.65, 2.94), (11.2, 2.94), (11.2, 9.7), (5.82, 9.7), (5.82, 9.55)], PURPLE, True
)
arrow([(11.2, 3.6), (10.65, 3.6)], PURPLE, True)
ax.text(8.7, 9.8, "辅助后续任务①规划／②恢复", fontsize=9.4, color=PURPLE, ha="center")
ax.text(
    0.4,
    1.1,
    "在线闭环：当前状态 → 选择动作 → 执行 → 再次观测",
    fontsize=12,
    color=BLUE,
    weight="bold",
)
ax.text(
    0.4,
    0.63,
    "经验闭环：历史轨迹 → 提炼与校验 → 检索后续状态 → 辅助决策 → 新结果",
    fontsize=12,
    color=PURPLE,
    weight="bold",
)
ax.text(
    0.4,
    0.2,
    "配置语义增强主要覆盖显式CMake BOOL；复杂依赖主要交Agent。经验是建议，不替代原测试、交付或重放。",
    fontsize=10,
    color="#728196",
)
for extension in ("png", "svg"):
    target = ROOT / f"system-overview.{extension}"
    fig.savefig(
        target,
        dpi=170,
        metadata={"Date": None} if extension == "svg" else None,
    )
    if extension == "svg":
        target.write_text(
            "\n".join(line.rstrip() for line in target.read_text().splitlines()) + "\n"
        )
plt.close(fig)
