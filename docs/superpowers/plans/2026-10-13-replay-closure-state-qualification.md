# H2 重放闭包状态资格实施计划

## 1. 冻结设计与身份

- 绑定 Issue #442、设计、预注册、实现 revision 和零 Provider 边界。
- 新建 create-once evidence root；历史 evidence 保持只读。

## 2. 提取可复用 replay 核心

- 让正式 replay 与 preflight 共用 recipe 构造和 `build.sh` 生成逻辑。
- 新增无 Session 终态副作用的 replay closure verifier。
- 结构化记录 recipe fingerprint、delivery fingerprint、退出码、失败分类和 cleanup。

## 3. 接入 Runtime v5/H2

- 新增 `workspace_ready` 与 `replay_closure_ready` 快照字段。
- 在现有 pre-freeze candidate verifier 之后执行 closure verifier。
- 失败时返回 bounded finding 并允许新 frontier 上继续命令和重试。
- 成功后才进入既有 candidate freeze；正式 evaluator 路径不变。

## 4. 测试

- 单元测试覆盖 fingerprint、分类、fail-closed、frontier 失效和提交门禁。
- 回归 Runtime v1-v4、CandidateVerifier、external evaluator 与 clean replay。
- 使用真实 Docker 运行三个正确构建系统夹具与两个已知缺陷 recipe。

## 5. 零 Provider qualification

- 先运行 Docker runtime preflight。
- create-once 写入 identity、每例结果、summary、marker 与 inventory。
- 审计 case 数、预期分类、误拦、cleanup、Provider/credential 计数和旧 evidence 哈希边界。

## 6. 决策

- 全部门槛通过：机制缺口修复合格，可设计新的未见样本 H0/H2 或 Workflow+Agent+Jev 比较。
- 任一已知缺口漏检、任一正确 recipe 误拦、cleanup 不闭合或 Session 被错误终结：停止进入 Provider 比较，先封口失败 identity 并重新设计。

