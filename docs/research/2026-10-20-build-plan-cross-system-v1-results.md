# 跨构建系统真实走读 v1：响应截断与测试失败

## 结果与决定

Issue #476；身份 `cpp-build-plan-cross-system-v1`。这是已见开发项目的真实模型接入走读，不是方法效果实验。决定：保留失败并进入独立 #478 输出截断修复，不向 v1 追加请求。

| 项目 | 实际执行 | 停止位置 | 结论范围 |
| --- | --- | --- | --- |
| zstd / Make | 没有执行构建命令 | 首响应 `finish_reason=length`，8192 completion tokens 全部为 reasoning，未生成方案；框架继续时超过60000字节消息上限 | 接入失败，不能评价模型能否完成该构建 |
| libusb / Autotools | 依赖、bootstrap、configure、build 成功；`make check` 执行全部四项，stress_mt 失败 | 恢复响应同样仅有8192 reasoning tokens；继续前被消息上限拒绝 | 初始规划及真实失败交接已执行；恢复未交付，严格完成未成立 |

libusb 初始方案保留 udev 和全部测试。测试失败的内部日志已采集，不能用它补填旧走读未保存的日志，也不能通过跳过 stress_mt 改写本任务。两个 Session 均失败终结，容器 cleanup 成功。没有 clean replay 成功或严格交付。

## 用量与证据

3次模型请求均有完整usage：43,601 input、21,643 output，共65,244 recorded tokens；冻结公开峰时价保守估算 `$0.1432596`，不是实际账单。没有本阶段未知usage预留。共享#470账本另有意外旧live测试 `$1` 未知费用预留。

原始证据：`/home/yiwei/.codex/outputs/forge-cross-system-model-v1/`，1006 files / 34,532,560 bytes；inventory canonical SHA-256 `2704868289b629da81532b0c8d91a15caf1d742b04cd41cede11c638a21dbc12`。独立只读审计：`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/cross-system-v1-audit.json`，`valid=true`。

身份定义：`benchmarks/manifests/cpp-build-plan-cross-system-v1.json`，SHA-256 `d1d88577bce265154a51fa813b30bb2cf781d1e788dbc26ac2a7f9b99f3039a2`；预注册同名 Markdown。执行前零Provider门禁目录 `forge-cross-system-gate-v1`、`forge-cross-system-gate-v2` 与真实模型结果分开封存。

## 下一步

新 v2 可增加单响应输出余量并在截断后立即停止，禁结构化解析隐式重试。继续固定源码、材料包、完整测试与验证；新结果只能说明修复后开发接入情况。当前结果不支持泛化、方法增量、自然恢复率或成本节省。
