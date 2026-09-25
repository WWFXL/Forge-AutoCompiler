# Phase 5 v2 资格门禁与 executable oracle 实施计划

日期：2026-09-25。设计：`../specs/2026-09-25-phase5-v2-qualification-oracle-design.md`。追踪：Issue #294。状态：**产品实现与非 Docker 回归完成，等待 PR、人工 qualification 和 v2 candidate 冻结**。

## 1. 交付顺序

- [x] 审计首次 Phase 5 candidate/session 原始 evidence，确认三项根因。
- [x] 创建并回读 Issue #294，从 `main@bc176d4b` 建立独立开发分支。
- [x] 冻结本设计和实施计划。
- [x] 先添加 executable policy 与 S2 分层的失败测试。
- [x] 实现版本化 policy、持久化 workdir 和 replay 对比。
- [x] 实现 S2 delivery/candidate/target 三集合规则。
- [x] 更新 Runtime 文档并运行快速定向测试与 Ruff。
- [x] 实现 Phase 5 v2 exact-commit qualification plan/protocol/runner。
- [x] 运行全部非 Docker 定向测试和确定性 identity 校验。
- [ ] 更新项目状态快照，提交并创建 PR。
- [ ] 使用人工 qualification result 冻结 Phase 5 v2 candidate identity 与正式 runner。
- [ ] 将耗时 Docker qualification 与完整回归命令交给用户运行。
- [ ] 根据用户返回结果修复问题或冻结 qualification，再单独设计授权修订。

## 2. 产品合同实现

修改 `schemas.py`、`operations.py`、`external_evaluator.py`：

1. 定义 `ExecutableVerificationPolicy` 及 schema/mode 校验。
2. 给 `BuildArtifact` 和 `ReplayArtifactComparison` 增加 smoke workdir 字段，旧 JSON 可按默认值加载。
3. submit 对默认模式保持现状；显式模式校验 command ownership 和成功状态，从 command log 固化结果。
4. replay 使用冻结 workdir，并比较 workdir identity。
5. evaluator 仅对单目标 executable 的成功 oracle 构造显式 policy。
6. S2 允许额外 support files，拒绝额外 compiled artifacts。

完成门：相关 unit tests 通过，默认调用方不需要改动。

## 3. Phase 5 v2 identity

新增而不修改旧 manifest/report/evidence：

1. qualification schema/protocol/runner，输出六项目 exact-commit 探测结果。
2. v2 candidate protocol，从已校验 qualification 生成 tasks 中的 capabilities 与 selected build system。
3. v2 runner 在 Provider 创建前复核 qualification digest 和运行时探测结果。
4. spec/preregistration 明确 0 Provider 开发边界、新 evidence 目录、非续跑语义和 Stage C 仍阻断。
5. deterministic tests 覆盖缺 task、commit 漂移、selected 不属于 capabilities、镜像漂移和旧 evidence 未修改。

完成门：无 Docker 的 generate/validate/delta 测试通过；candidate identity 只有在 qualification result 存在且有效时才能冻结。

## 4. 本地快速验证

由开发过程运行：

```bash
cd backend
uv run pytest tests/test_external_evaluator.py tests/test_compile_runtime.py -q
uv run ruff check packages/harness/deerflow/compile tests/test_external_evaluator.py tests/test_compile_runtime.py
```

测试若仍偏长，将进一步缩到本次新增 test node；不运行真实 Provider、Docker replay 或正式实验。

## 5. 用户执行的长任务

代码合并前，由用户运行届时提供的固定命令：

1. 六项目 Docker exact-commit qualification。
2. compile runtime/external evaluator 完整后端回归。
3. 必要的 Docker clean replay 门禁。

命令必须把日志和结构化结果写入独立临时路径，不得写首次 Phase 5 evidence。用户返回 exit code、日志尾部和 qualification result SHA-256 后再继续。

## 6. 停止条件

- 需要修改首次 Phase 5 manifest、report 或 evidence。
- 显式 oracle 无法在 replay 中复现同一 command/workdir/result。
- qualification 不能在模型创建前完成或无法保证 cleanup/0 orphan。
- 非 Docker 单元测试必须访问 Provider 才能建立。
- 新 identity 需要改变公共 prompt、预算或停止规则。
