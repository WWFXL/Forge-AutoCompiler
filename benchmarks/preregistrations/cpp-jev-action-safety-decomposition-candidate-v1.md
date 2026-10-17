# Jev 逐动作安全判断问题分解候选预注册

## 身份

- Candidate identity：`cpp-jev-action-safety-decomposition-candidate-v1`
- Planned formal identity：`cpp-jev-action-safety-decomposition-v1`
- Tracking Issue：[#465](https://github.com/WWFXL/Forge-AutoCompiler/issues/465)
- Manifest canonical SHA-256：`a53487b447e2c14d113a65b773520244a962d55114b418e0fe543053ff8d0de6`

## 冻结设计

父 outcome 与 #463 Jev evidence 保持只读。四选一只作冻结 calibration 历史对照，
不运行其旧 evaluation。新实验比较 `action_noul` 与 `action_card_noul`；每个状态在
一个请求内按正序和逆序各询问三个 Noul，动作原始分数固定为两次真概率的最小值。

每个 condition 在 15 个 calibration 状态的 45 行上独立拟合一维 Platt scaling，
并选择使最低成本动作选择器零 observed unsafe direct、覆盖最大的阈值。该阈值只在
另 3 个项目族的 15 个 evaluation 状态上应用一次，随后复用父六维 BudgetFit。

## 当前权限

当前仅授权生成和验证候选合同、mock SDK、父 evidence 审计及 credential 文件元数据
检查。当前不授权读取 credential 内容、调用 Provider、创建 formal attempt/evidence
或实现 controller。

## 未来预算与停止规则

授权 identity 的硬上限计划为 60 requests、400,000 input tokens、100,000 output
tokens 和 `$0.0168`；固定 `jev-1.13.0`、30 秒 timeout、SDK retry 0。失败请求不
retry，不 replacement，不 backfill。结果后不得修改 prompt、split、calibrator、
threshold、label 或 decision rule。

资格门槛、TF-IDF 对照与解释边界以 spec 和 manifest 的 const 内容为准。候选通过只
允许创建绑定 exact implementation revision 的 authorized manifest，不构成 Jev 效果
证据。
