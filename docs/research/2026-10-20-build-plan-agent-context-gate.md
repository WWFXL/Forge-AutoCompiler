# 读取反馈与证据工作集修复门禁

Issue #489；独立 `cpp-build-plan-agent-canary-v2` 前置工程门禁，真实模型尚未调用。保持v1四个固定任务、模型、镜像、完整测试、严格交付、资源和顺序。新增安全路径别名、可恢复读取拒绝反馈、带来源的有界证据工作集，修复初始miniz README大小写材料；不扩大授权读取根、不改源码或测试、不降低验收。

每个真实Docker臂先通过LangChain图执行`list_source('/workspace/repo')`和一个预定不存在目录的读取：前者成功，后者返回可见拒绝，之后继续完整参考构建。8/8 strict completed、固定源码未变、完整测试/精确交付/clean replay/cleanup通过。plan每臂2次、tool每臂3次脚本化请求；0Provider、0模型tokens。这验证读取错误不会再终结整臂，不是模型效果观察。

5项新回归验证别名、越界与链接逃逸、缺失文件反馈、跨最近三次交互的真实证据保留、24000/4000字节边界以及权威状态不裁剪。默认产品1880 passed/44 skipped，Ruff check/format通过。旧临时目录权限清理警告未处理，不修改历史证据。

门禁原始：`/home/yiwei/.codex/outputs/forge-plan-agent-canary-gate-v2/`。
3445普通文件、24链接、90,498,214 bytes，inventory canonical SHA-256
`6e76caae9f29916ad29f2036e382e8c8c7c77d07976466de4415713cfe2103dd`。
外部独立审计 `forge-continuous-research-2026-10-19/plan-agent-canary-gate-v2-audit.json`，valid=true；额外逐臂检查原始工具反馈确有成功读取及缺失拒绝。
manifest SHA-256 `549dbbd1f9b28f5cfe2d012dce67406124428da912dc55230b9675d9b50a64b5`。

下一步按既有授权预留$12运行唯一真实8臂v2，累计共享$20；已有已知估算$0.74375004及未知预留$1。v1永久只读，修复后开发接线与旧失败不作因果比较；没有状态变化或修订激活时不声称状态适应有效。运行中不得修改冻结components。
