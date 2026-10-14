# 进展预算感知 Jev 离线校准 candidate 实施计划

## 1. 阶段定位

- Tracking Issue：[#461](https://github.com/WWFXL/Forge-AutoCompiler/issues/461)；
- 上游 spec：[#459](https://github.com/WWFXL/Forge-AutoCompiler/issues/459)；
- 父资格 identity：`cpp-progress-budget-jev-identifiability-qualification-v1`；
- 本阶段类型：实验基础设施；
- 本阶段结果：只能说明协议和执行前门禁是否闭合，不产生 Jev 效果、controller 效果或端到端成本结论。

本阶段把 spec 固定的项目族隔离、Jev 请求、响应解析、校准、BudgetFit、门槛和停止规则落实成可确定重建的 candidate。Provider 执行必须在 candidate 提交、推送和审查后另建 authorized identity。

## 2. 阶段 1：父证据与 split 绑定

1. 只读校验父报告、父 manifest、completed marker 和 702-file inventory 的文件与 canonical SHA-256。
2. 按父 source pool 中冻结顺序机械划分项目族：

| Build system | Calibration | Evaluation |
| --- | --- | --- |
| CMake | `github.com/p-ranav/argparse` | `github.com/neargye/magic_enum` |
| Make | `github.com/kgabis/parson` | `github.com/antirez/sds` |
| Autotools | `github.com/troglobit/libuev` | `github.com/ivmai/libatomic_ops` |

3. 对每个 split 固定 state、provider state、action label、budget decision、RuleGate 和 TF-IDF 行的 canonical SHA-256。
4. 机械复核每侧 3 个项目族、15 个状态、45 个 matched budget decisions，项目族和状态不重叠。
5. 重新计算 evaluation 的冻结基线：RuleGate `27/45` joint correct、30 direct、18 wrong direct；TF-IDF+BudgetFit `39/45` joint correct、18 direct、0 wrong direct；Oracle route 为 direct 24、escalate 3、stop 18。

完成标准：任何文件、split、规模或基线漂移均 fail closed，不能生成或通过 candidate。

## 3. 阶段 2：Jev 与校准合同实现

1. `provider_state` 只输出 `build_system`、`phase_facts`、`progress_facts` 和 `semantic_failure_log`。
2. 每状态一个请求，同一请求包含正序和逆序两个 Choice；固定 `jev-1.13.0`、30 秒 timeout 和 `max_retries=0`。
3. mock transport 检查 endpoint、Authorization 注入位置、模型、state 字段和 Choice 顺序；mock key 只存在于内存测试，不读取真实 credential。
4. 响应解析检查模型版本、request ID、usage、概率有限性、完整 key、概率和容差、argmax Choice 和 confidence 公式；通过后才归一化概率。
5. 固定 45 行 local-action Platt scaling：`LogisticRegression(C=1.0, solver="liblinear", random_state=459, max_iter=1000)`。
6. 固定 calibration-only threshold：在顺序一致且 top-1 为 local action 的状态中，选择零 observed unsafe direct 下覆盖最大阈值；覆盖并列取更高阈值。

完成标准：mock SDK、无泄漏 state、响应漂移拒绝、45 行校准和阈值选择均由聚焦测试覆盖。

## 4. 阶段 3：BudgetFit 与零 Provider preflight

1. 复用父 manifest 冻结的三类预算、三个 local action charge 和 Agent reservation。
2. 路由顺序固定为：通过校准且预算可容纳的 local action -> `direct`；否则预算可容纳 Agent reservation -> `escalate_agent`；否则 `stop`。
3. Jev 请求成本单独记录，不回填父 continuation budget；端到端实验必须在未来共同预算中计入。
4. preflight 校验 candidate manifest/schema、父 evidence inventory、SDK 版本、scikit-learn 版本、plan/preregistration 和 mock SDK。
5. credential 检查仅报告环境变量是否存在、`jev-apikey.txt` 是否存在/是否符号链接/文件模式；禁止读取或输出值。

完成标准：preflight 明确报告 0 Provider、0 credential content read、0 token、0 formal attempt/evidence write 和 0 historical evidence write。

## 5. 阶段 4：验证与发布

1. 确定性复生成 manifest 与 const JSON Schema，确认无 diff。
2. 运行聚焦 pytest、相关 Jev candidate 回归、Ruff、format check、`py_compile`、`git diff --check` 和敏感信息扫描。
3. 更新 `RESEARCH_STATUS.md` 和 `.claude/memory/project.md`，明确本阶段没有新增效果 evidence。
4. 提交、推送堆叠分支并创建中文 PR，回读 PR 正文并等待 CI。

## 6. 权限与停止边界

本阶段允许读取父报告和冻结 evidence，允许创建 candidate 文档、代码、测试和 GitHub Issue/PR。明确禁止：

- 打开或读取 `jev-apikey.txt` 内容；
- 读取 `TYPESAFE_API_KEY` 的值；
- 调用 TypeSafe Provider、Jev 或完整 Agent；
- 创建 authorized/formal execution identity 或 Provider evidence；
- 修改、续跑、替换或回填任何父 evidence；
- 实现 Workflow controller；
- 把基础设施通过表述为 Jev、BudgetFit 或动态预算效果。

candidate 审查完成后，下一项研究决策才是是否建立独立 authorized calibration identity。该 identity 必须绑定 exact Git revision、30 请求、200,000 input tokens、50,000 output tokens、`$0.0084` 费用上限和 spec 中的停止规则。
