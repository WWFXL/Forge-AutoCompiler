# Symlink-safe checkpoint restore gate 设计

> 日期：2026-10-12
> Tracking Issue：[#425](https://github.com/WWFXL/Forge-AutoCompiler/issues/425)
> 工作类型：工程修复与基础设施门禁

## 1. 阻塞问题

动态预算轨迹资格 v4 在恢复 `autotools-libestr-state-3` 时，Python 3.10 `tarfile.data_filter` 将 `src/.libs/libestr.la -> ../libestr.la` 的目标按解包根目录解析，而 tar symlink 应按链接成员的父目录解析。合法目标 `src/libestr.la` 因而被误判为 destination 外路径。

该失败发生在 continuation 执行之前，只能说明 checkpoint restore 基础设施缺口，不评价 Autotools action、动态预算、Jev、Agent 或 controller。

## 2. 安全语义

1. 所有成员继续经过标准 `tarfile.data_filter`，保留成员路径 containment、权限收缩、owner 清除和特殊文件拒绝。
2. symlink 的相对目标按 `dirname(member.name) / member.linkname` 归一化后交给标准 filter 校验；落盘时保留原始 `linkname`。
3. hardlink 的 `linkname` 继续按 tar archive root 解释，不套用 symlink 父目录语义。
4. absolute symlink、真实 `..` 越界、越界 hardlink、device、FIFO 和经已有 symlink 写出 destination 的成员全部拒绝。
5. 解包只发生在 destination 同级临时目录；完成全树 symlink containment 和可选 tree hash 验证后，才原子发布 destination。失败时删除 staging，不留下部分恢复目录。

## 3. 门禁矩阵

| Case | 预期 |
| --- | --- |
| `src/.libs/libestr.la -> ../libestr.la` | 接受，链接文本和内容解析均保持 |
| `src/.libs/escape -> ../../../outside` | 拒绝，不发布 destination |
| absolute symlink | 拒绝，不发布 destination |
| archive-root 越界 hardlink | 拒绝，不发布 destination |
| character device / FIFO | 拒绝，不发布 destination |
| tree hash mismatch | 拒绝并清理 staging |
| v4 `libestr` workspace checkpoint | 只读恢复，tree hash 与冻结 message 相同 |

## 4. 通过与解释边界

全部门禁通过后，决定为 `proceed_to_dynamic_budget_trajectory_qualification_v5_design`，只解除全新 v5 的恢复基础设施阻塞。失败则为 `stop_before_dynamic_budget_trajectory_qualification_v5`。

本 gate 不读取 credential、不调用 Provider/Jev/Agent、不创建 formal experiment identity、不续跑 v4，也不修改 v1-v4 runner、报告或 raw evidence。
