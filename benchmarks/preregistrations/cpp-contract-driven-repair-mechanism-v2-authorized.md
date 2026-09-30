# 契约驱动修复 mechanism v2 release-bound identity

## 性质

本 identity 把 Issue #367 / PR #368 发布的独立 36-arm candidate 绑定到 exact scientific-contract release `70b257c840f4065285c047ba6207ffe99f8dcb36`。父 candidate canonical SHA-256 为 `40ea47064e7345a03c1d4dbbe13316f4e3575e29c561709d6561a135c4e25f0d`，文件 SHA-256 为 `9d60eeb76f4426fca1dc44f759986a4d4f93ba496be7cc8158ac3d88c0cb22c4`。

该阶段只冻结 release 和组件身份，不授权真实执行，不生成研究 observation。合并后允许 `validate`、`plan` 和不读取 credential 的 `preflight`；`availability`、`batch`、`report` 与 `audit` 保持 fail-closed。

## 不变合同

以下字段逐字继承父 candidate：

- 6 projects / 12 matched checkpoints / 36 C0-T1-T2 arms；
- 36 个 opaque clone IDs 与 36 个 opaque evaluation IDs；
- delivery/target 与 provenance strata、condition 顺序和反馈 projection；
- DeepSeek `deepseek-flash` 配置、无 token ceiling、逐请求计量；
- per-arm budget、288 request-attempt 机械上限、transport retry 与早停规则；
- strict endpoint、external evaluator、clean replay、cleanup 和分析规则；
- 独立 evidence root `.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent`；
- v1 sequence 1 永久排除和全部历史 evidence/outcome 不导入的声明。

## 权限边界

仅 `identity_implementation_authorized=true`。以下权限均为 false：credential read、Provider call、model creation、model token、Docker formal Session、availability execution、formal collection、formal attempt 和 formal evidence write。嵌套 availability execution 同样没有任何真实执行授权。

Preflight 只核对 clean `main == origin/main`、release 后代关系、父 manifest 与组件 hashes、冻结 image ID、零 managed resources、v1 失败 evidence inventory 未漂移，以及 v2 evidence root 不存在。它不读取 credential，不创建 container、marker、attempt 或 evidence。

## 下一门禁

本 identity 合并并通过 clean-main preflight 后，研究负责人仍需对一个新的 execution identity 明确授权。该 execution identity 才能在 v2 evidence root 中创建独立 availability marker；availability 通过并冻结审计后，才能启动 36-arm batch。

本阶段证据仅支持 release-bound 身份闭合，不支持 treatment effect、显著性、总体成功率、Provider/model 排名或跨项目外推。
