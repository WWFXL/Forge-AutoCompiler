# 输入输出Token与规划恢复阶段费用归因审计

Issue #514，身份`cpp-build-token-cost-attribution-audit-v1`，0Provider/0Docker/0凭据的回顾结果分析。输入固定#502全部24臂与#504全部12臂，两批结果均已见，价格贡献和libverto恢复次数也已初步观察；不是前瞻假设检验。UTC22:45前执行，旧raw和失败保持只读。

逐响应读取AI usage_metadata，校验input+output=total、事件Token、请求生命周期与官方臂总计；缺usage/未知用量、错配或原队列缺行则fail closed，不挑选成功子集。按agent.started事件标记initial/recovery，且每个plan实际请求payload的handoff存在性必须一致；工具臂统一tool。原失败臂全费用保留。价格沿原协议保守估算input $1.32/M、output $3.96/M，不视为账单或缓存实付。

每队列分别输出plan/tool、每项目及阶段的请求/输入/输出/费用。差分解为输入贡献差+输出贡献差，严格守恒，不按阶段丢弃费用。不得池化两个队列的成功率、作跨批自动ID因果、总体成本优势、模型排名、自然恢复率或状态选择器增量。请求次数、总Token和费用是不同指标；不因观察到某队列反转而调整分母、价格或判定。

前后完整核验两父typed inventory；记录全部实际消费文件SHA/大小/路径并再次核验，封存代码/测试/协议与结果。独立审计应直接逐响应复算，不调用本提取器aggregate/inspect_arm。6项测试覆盖失败成本保留、恢复双来源、缺usage/错价/未知用量拒绝和输出价格权重；最终结果head三CI后发布。该分析不追加真实调用或改变任何既有实验身份。
