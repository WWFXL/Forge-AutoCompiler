# Jev 未见项目族正式三臂比较 v2 资格失败

- 决定：`supersede_with_fresh_v3_identity`
- 阶段：零 Provider qualification
- 完成：前 `6/12` 个项目均通过 S0-S5 和 clean replay
- 停止：第 7 项 `ffmpeg` 的冻结修复动作生成了自包含 Makefile
- Provider / credential / formal attempt：`0 / 0 / 0`

v2 先删除受控故障写坏的顶层 `Makefile`，再运行 FFmpeg `configure`。该项目的顶层
`Makefile` 是受版本控制的源码文件；删除后，`configure` 生成了仅含 `include ./Makefile`
的自包含文件。后续 `make -j4 ffmpeg` 因递归打开同一文件，以
`Makefile:1: *** Too many open files` 退出。这不是对象文件或依赖文件残留导致的资源耗尽。

在独立副本、同一 `autocompiler:gcc13` 镜像和 `nofile=1024` 限制下，先执行
`git checkout HEAD -- Makefile`，再运行相同 configure 与 build，`make -j4 ffmpeg` 和
`./ffmpeg -version` 均返回 0。该诊断只验证基础设施修复，不是资格或 treatment evidence。

失败项与前六项均已终结且无受管资源；正式 evidence root 和资格报告均未创建。v2 不续跑、
不 replacement、不 backfill；v3 只允许将 FFmpeg configure repair 改为恢复 tracked
`Makefile` 后重新配置，并从 12 项资格门禁重新开始。
