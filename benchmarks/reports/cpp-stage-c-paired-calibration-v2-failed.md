# Stage C v2 首个 pair 中断审计

日期：2026-09-26。来源 identity：manifest canonical SHA-256 `5a479832a2a6f9bdc49407a35b3ccc997547365fa65273d19fda4d1b4516eee4`，release `b947846580be9db20cc8b5c3c41b89b1eb4212e6`。

## 结论

- v2 唯一 reachability 已通过，消耗 1 request / 70 recorded tokens。
- batch marker 状态为 `started`，没有完整 pair。
- `stage-c-v2-json-c-r1` 的 A 臂已登记并闭合，消耗 4 requests / 41,861 recorded tokens；结果为 `strict_reproducible_build_success=false`，错误分类为 `method_error:FileNotFoundError`。
- 同一 pair 的 B 臂在写入 `attempt.json` 前再次获取相同 exact commit，遇到 GitHub GnuTLS 连接中断；B 臂没有正式 attempt、模型请求或 result。
- v2 合计 5 Provider requests / 41,931 recorded tokens / 1 formal arm。依据预注册停止规则，已有正式 A attempt 的未闭合 pair 永久阻断 v2；不得删除 evidence、补跑 B、重试 A 或继续后续 pair。
- 停止后没有 Stage C 或 Compile managed container 残留。

## 根因

### Pair 源码边界

v2 将源码准备移到各 arm 的 `attempt.json` 之前，但 A、B 仍分别从 GitHub 获取同一 exact commit。这样只能保护“首个 arm 前失败”，不能保护“A 已闭合、B 尚未登记”之间的网络故障。下一 identity 必须在 pair 的首个正式 attempt 前完成一次 exact source acquisition 和 snapshot 校验，再从同一不可变快照为两臂创建独立副本。

### A 臂产物验证边界

A 臂第一个 Dockerfile 因 header 安装路径错误而正常构建失败。模型修订后的第二个 Dockerfile 已成功生成 `include/json-c/json.h` 与 `lib/libjson-c.a`，但 runner 在编排容器中复用 qualification 的 `_artifact_evidence`，该函数调用宿主 `file` 和 `ar`。`deer-flow-langgraph` 不含 `file`，因此 Python 抛出 `FileNotFoundError`；受控基线只保留异常类型，最终候选未提交。

下一 identity 的 A 臂必须在冻结 Stage C candidate image 中运行产物类型与静态库成员检查，编排容器只负责结构、大小和 SHA-256 复核。这样验证工具来自已冻结镜像，不再依赖 orchestrator 的偶然软件集合。

## 后续边界

v3 使用新的 manifest、schema、evidence 目录、pair/attempt ID、reachability 和完整 48-arm batch。v2 outcome 不导入 v3 分析。任务、顺序、A/B 方法、Provider/model、Stage C image、每臂预算、evaluator、S0-S5、严格成功定义和 project-level 配对口径保持不变。

机器可读审计包含现有 425 个 evidence 文件的路径、大小与 SHA-256，见 `benchmarks/reports/cpp-stage-c-paired-calibration-v2-failed.json`。
