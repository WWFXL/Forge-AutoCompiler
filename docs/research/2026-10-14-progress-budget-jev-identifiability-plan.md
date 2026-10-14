# 进展预算感知 Jev 联合 benchmark 执行计划

## 阶段 1：结果盲来源资格

1. 选择此前未进入 Forge 动作或效果 benchmark 的 CMake、Make、Autotools 项目族各 2 个。
2. 在固定 `autocompiler:stage-c-v1` 镜像中验证 exact commit、禁网 reference build、真实产物和 functional oracle。
3. 在 outcome matrix 之前冻结 source archive、license、项目配额和预冻结排除项。

## 阶段 2：协议与实现冻结

1. 冻结五类状态、四类动作、三类预算、真实结果标签规则和停止条件。
2. 实现 create-once runner、完整日志、动作前后状态、预算增量、严格 replay 和独立 audit。
3. 用单元测试验证 manifest/schema 常量、路由标签、预算可行性、基线和 replay recovery 判据。
4. 在正式 outcome 前提交并推送协议 revision；工作树只允许既有用户未跟踪 HTML。

## 阶段 3：唯一正式零 Provider 采集

1. claim 新 evidence root 和唯一 attempt。
2. 每个项目执行两次 reference closure。
3. 每个项目、状态、动作执行两次独立 branch；失败、超时和部分结果全部保留。
4. 从 outcome matrix 确定安全动作和 route label，计算 RuleGate 与 TF-IDF 基线。
5. 生成 inventory、完成 marker、版本化 JSON/Markdown 报告并执行独立 audit。

## 阶段 4：决策

- 通过：只进入 Jev Provider calibration 设计，尚不实现完整 controller。
- 失败：停止 Jev calibration 和 controller，实现与结果均作为 benchmark 负证据封存。
- 无论结果如何，冻结 evidence 不续跑、不回填、不替换项目。
