# Phase 5 v2 结果审计与 evaluator v3 设计

日期：2026-09-25。追踪：Issue #299，关联 Issue #297、#291。

## 问题与结论边界

Phase 5 v2 的唯一六项目 batch 已闭合，原始报告必须保持只读。原始统计是 generated 6/6、submitted 5/6、strict 1/6、bitwise 2/6。审计发现 `openh264`、`c-ares`、`libass` 的系统 functional oracle 复用了 Agent 的 `run_container_bash` 内部路径，因此在 Agent 已耗尽 post-build inspection budget 后统一以 policy exit 126 被拒绝。这三项不能归因于模型，也不能追认为成功。

审计后的描述性分类固定为：1 项可靠成功（`cppitertools`）、2 项工作流失败（`yyjson`、`uwebsockets`）、3 项 evaluator 缺陷导致不可判定。该分类是事后审计，不产生无偏成功率主张；Stage C 继续阻断，当前 batch 不重跑、不 retry、不 replacement、不 backfill。

## 冻结边界

- 不修改 `external_evaluator_v2.py`、Phase 5 v2 authorized protocol/runner、manifest、Schema 或 `.compile-sessions` 下的原始 evidence。
- 审计工具只读取并校验原始报告、决策包、task result、Session、evaluator 日志和 node event hash chain，报告写入新的版本控制路径。
- v3 使用新的 evaluator version/rules identity。任何后续真实运行必须另行设计授权 manifest、独立 evidence 目录和 attempt identity。

## 系统 oracle 执行权限

`run_container_bash` 的 Agent 工具 schema 保持不变。共享私有实现增加一个仅 Python 内部包装器可提供的 opaque authority；默认调用仍执行 post-build forbidden-role 检查并消费 inspection budget。v3 oracle 通过该包装器执行时：

- 跳过 Agent post-build 次数门禁及其消费；
- 继续拒绝 `/repro` 访问、关闭严格 shell、混合逻辑阶段和冻结构建参数漂移；
- 继续生成 `BuildCommandRecord`、完整 command log 和 workflow event；
- 不释放、不修改 Agent 剩余 budget。

## Evidence ownership

新增通用 host ownership 规范化器，读取成对的 `FORGE_HOST_UID`/`FORGE_HOST_GID`。它拒绝符号链接根，不跟随树内符号链接，保留 owner/group 可执行位并清除 other 权限。新的 `ExperimentLedger` 每次原子替换后立即规范化 ledger；后续 benchmark runner 可在终态规范化整个独立 evidence tree。当前 root-owned Phase 5 v2 evidence 不做 chmod/chown。

## 输出语义

新的审计 JSON/Markdown 同时保留 raw verdict 和 audit classification，并把 `execution_completed` 与 `strict_success` 分成不同字段。CLI 只打印固定长度摘要，完整 task evidence 仅写报告文件，避免终端再次被 outcomes 截断。

## 验收

- post-build budget 为 0 时，Agent smoke 仍以 policy exit 126 拒绝。
- v3 系统 oracle 能执行、记录命令与日志，且 Agent budget 保持为 0。
- v1/v2 evaluator 与 authorized runner 的 SHA-256 保持冻结值。
- 审计工具可确定性复算 1/2/3 分类、raw 1/6 strict、Stage C false 和禁止重跑。
- ownership 测试证明宿主 UID/GID 生效且符号链接目标不被遍历。
- 后端相关测试、完整测试与 lint 通过。
