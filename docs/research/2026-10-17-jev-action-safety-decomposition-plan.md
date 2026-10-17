# Jev 逐动作安全判断问题分解执行计划

## 阶段 1：零 Provider 协议与实现

1. 固定 spec、candidate manifest、const schema 和 preregistration。
2. 实现 ActionCard 机械归纳、两个 Noul condition、顺序重复问题和响应校验。
3. 实现 Platt、选择器级零错误阈值、BudgetFit、指标和唯一决策逻辑。
4. 用 `httpx2.MockTransport` 验证 SDK wire shape、Noul 返回、retry=0 和敏感字段排除。
5. 审计父 report/evidence 与 #463 evidence hash；旧文件保持只读。

出口：候选合同可确定重建，测试通过，零 credential 内容读取、零 Provider、零新 formal
attempt。

## 阶段 2：冻结执行身份

1. 提交并推送完整 runner 和 candidate 合同。
2. 用该提交作为 implementation revision，生成 authorized manifest、const schema 和执行
   amendment。
3. 再次执行零 Provider preflight，确认分支、revision、runner hash、egress、credential
   mode、预算和 evidence root。
4. 提交并推送 authorized identity；正式执行时 HEAD 必须包含且 runner 精确匹配
   implementation revision。

出口：新 identity、最大 60 requests / 400k input / 100k output / `$0.0168` 和停止规则
不可变。

## 阶段 3：正式数据采集

固定顺序：

1. `action_noul/calibration` 15 请求；
2. `action_card_noul/calibration` 15 请求；
3. 冻结两个 Platt 模型与阈值；
4. `action_noul/evaluation` 15 请求；
5. `action_card_noul/evaluation` 15 请求；
6. 一次性生成 evaluation 分析与最终决定。

任一物理请求或合同失败都保留已有 attempt/observation 并失败关闭，不补跑其余状态。

## 阶段 4：审计与结论

1. 封存 result、terminal marker 和 inventory。
2. 独立重算请求、usage、费用、阈值、指标和父 evidence inventory。
3. 扫描 credential、Authorization 和 Bearer 泄漏。
4. 生成 JSON/Markdown report，更新 `RESEARCH_STATUS.md` 与
   `.claude/memory/project.md`。
5. 提交、推送并创建中文 PR；回读 PR 内容和 CI 状态。

完成不是“写完 controller”，而是能够根据冻结门槛区分问题结构、动作上下文和模型
能力，并明确 Jev 是否仍值得进入 controller replay。
