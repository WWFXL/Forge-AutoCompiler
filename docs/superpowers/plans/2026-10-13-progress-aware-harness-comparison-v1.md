# 进展感知结构化 Harness H0/H1 配对比较 v1 实施计划

## A. 冻结身份

- [x] 确认 tracking Issue #433 和 H1 qualification v2 正向门禁。
- [x] 固定 H0/H1 treatment、9 个 checkpoint、3 次重复、配对顺序、模型、预算、费用和停止规则。
- [x] 固定每项目 state-1 离线 source archive，历史 evidence 保持只读。
- [ ] 完成 manifest、Schema、预注册、runner 和组件哈希。

## B. 零 Provider 工程门禁

- [ ] 静态验证 27 pairs / 54 formal arms、3 pairs / 6 canary arms 和交错顺序。
- [ ] 验证 H0 调用 Runtime v3、H1 调用 Runtime v4，其他合同一致。
- [ ] 验证 source archive 绑定、预算守恒、create-once、completed-prefix continuation 和 fail-closed。
- [ ] 在干净且已推送 release 上运行 Q0，要求 9/9 strict、离线 replay 和 cleanup 通过。

## C. Provider canary

- [ ] Q0 通过后读取 `DEEPSEEK_API_KEY` 的存在性，不记录其值。
- [ ] 运行 3 个配对 canary，共 6 arms。
- [ ] 只检查分类终结、token/预算、checkpoint/source、严格裁判和 cleanup；不形成效果结论。

## D. 正式配对实验

- [ ] 按 manifest 顺序运行 27 pairs / 54 arms；每个 arm 仅一次物理 attempt。
- [ ] 每个 pair 后核对累计 request、token、费用和 0 managed resources。
- [ ] 保存 H0/H1 事件、Session、candidate、S0-S5、source snapshot、clean replay 和 cleanup 证据。

## E. 分析与封口

- [ ] 计算 strict success、聚类 bootstrap、成本差、长尾与 Harness 机制指标。
- [ ] 按预注册联合门槛给出通过或停止决定，不修改阈值或分母。
- [ ] seal inventory，生成 JSON/Markdown 报告并更新 `RESEARCH_STATUS.md` 与 `.claude/memory/project.md`。
- [ ] 运行聚焦测试、冻结 benchmark 测试和 evidence audit。

## 边界

- 不修改或回填任何历史 evidence；不 retry 已开始但无结果的 arm。
- 不接入 Jev、动态预算 controller、Claude Code 或 Codex。
- 不因 canary 或正式中间结果更换模型、checkpoint、预算、顺序或终点。
