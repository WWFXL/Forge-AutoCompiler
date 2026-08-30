# OpenH264 provenance 单配对 execution amendment

- Issue：[#226](https://github.com/WWFXL/Forge-AutoCompiler/issues/226)
- 父候选：Issue #224 / PR #225，`main@185fcbed4e7ad01f6eae6cb247304601f480f83f`
- 性质：全新 OpenH264 evidence identity；不是 #218 retry、replacement 或 backfill。

## 执行授权

Provider 固定 DeepSeek `deepseek-v4-flash`、`https://api.deepseek.com`、300 秒、0 retry、非 streaming、禁止 fallback。只允许一次 reachability；成功后只允许一个 `baseline -> treatment` state-matched pair。每臂最多 8 requests、8 turns、24 graph steps、120,000 recorded tokens；阶段总上限 245,000。

## 运行时边界

Runner 复用冻结 #218 lifecycle 编排，但把 OpenH264 lifecycle adapter、#220 正确 parity/observability bindings 与本 manifest protocol 注入同一受保护上下文；不得再把 candidate module 同时伪装成 parity 与 observability。合并后 preflight 必须再次通过 #224 static gate 与完整 fake-model agent construction。

基础编译镜像缺少 `nasm`。Pair 前仅允许一次 dependency fixture：下载固定 `nasm 2.16.01-1build1 amd64` 包并校验 SHA-256 `22eede0f2dd62343b0298182f62f7485704fe02f166395b02c92a8883377e0b3`，通过精确命名 prep container 安装后 `docker commit --no-pause` 为 manifest 固定 tag。失败 marker 终结后禁止再次准备；pair 完成或失败后必须删除 prep container、tag 与实际 image ID。

## 证据与停止规则

Reachability、dependency fixture、pair、checkpoint、parent/arm ledger 与 canary report 使用全新目录和路径。Reachability 失败即停止；identity、fixture、预算、cleanup 或未分类失败即停止。Endpoint timeout 只删失当前 arm 并继续另一 arm；分类后的 arm outcome 继续配对。禁止 retry、replacement、backfill 或 extension。

结果只做单 pair 描述性机制复制。不得与 #218 无效 hoextdown pair、CMake pair 或其他 Make case 池化，不计算 p 值，不排名模型。
