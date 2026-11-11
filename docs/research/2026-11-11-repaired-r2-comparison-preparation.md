# 修复后共同基座上的H0/R2比较准备

用户要求针对上一轮实验，在新基座重新比较。新身份为`cpp-build-recovery-harness-r2-repaired-comparison-flash-v1`，Issue #731；当前是实验准备，尚无正式结果，0/36、0 Provider、0新增模型费。

## 已固定范围

沿用E54的18项目、三系统各6、各方法每项目一次共36槽；同版本源码/镜像/简洁主目标，不追加样本。每项目重新一次共同H0规划，两个干净会话共享完整方案。只改变自然失败后的恢复指导：H0为空，R2保留已审核270becfd指导及来源原文，只显式重新绑定修复后共同提示哈希；旧候选及旧底座守卫原样保留。主项目参考仅masscan换成#729作者源码有依据的exit(1)，原命令/输出/主组件不变，两组共享。

共同运行版本包含PR #730全部修复。旧E54原证据和失败不回写，新批不混旧分母。相同项目已有暴露，不能称未见泛化；新规划含随机性，不能将跨批差值全归因于共同修复。结果先向用户审核，不自动写论文，H0仍默认。

## 入口与检查

[预注册](../../benchmarks/preregistrations/cpp-build-recovery-harness-r2-repaired-comparison-flash-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-recovery-harness-r2-repaired-comparison-flash-v1.json)、`scripts/forge_recovery_harness_repaired_comparison.py`；复用既有execute、paid_callbacks及按实际分母分析，不添加新的Agent或工具。

5项新增及6项既有相关检查全部通过（11项）：只改共同提示绑定且旧守卫仍拒绝、18项目/源码/任务保持、masscan共享参考、生产回调装配两种指导与同输入、旧授权不能运行新身份；prepare/check-prepared验证源码归档及组件哈希。既有pytest临时目录权限清理告警另存，不改变本次测试结果。此前三项目真实构建、重建及mozjpeg材料验证复用#729证据，不重复构建充当效果。

建议正式费用硬上限5美元、确认起4小时；deepseek-flash thinking low；无自动重试、不补槽，未知用量/模型标识异常/清理失败停止整批。所有规划、读取、失败、纠正与恢复费用计入，历史提案费另列。用户已授权5美元/4小时，UTC2026-11-11 03:21:11—07:21:11。首轮CI仅因测试尝试访问本机归档失败，现测试单独模拟外部归档摘要，生产门禁及运行代码不改；修复后5项新测试通过。发布及CI以PR732为准，正式运行在其检查后启动。
