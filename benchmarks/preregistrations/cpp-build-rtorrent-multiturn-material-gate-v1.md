# rtorrent 多轮材料零 Provider 资格 v1

跟踪 #591。基础设施/工程修复；只核验新共享JSON值表示及既有实际middleware，不研究模型效果。旧v2三槽失败不回填，无自动重试。本资格不读取模型凭据、不构造Provider、不执行源码或Docker；原用户共享窗口UTC2026-10-21 19:30:52结束，不延长。

固定分母30：v2全部28实际请求，加槽1/3各一个最后停止材料。每例来源、SHA及组件冻结见同名manifest。实际请求取其精确projected/encoded匹配收据；两个停止包以末projected、最后三个tool.completed和终态usage重建remaining_budget。停止包的elapsed为末snapshot重建，不能伪称原未落盘请求的精确字节或耗时。

通过真实SharedValueMeter→ContextCanaryMeter→CanaryMeter.wrap_model_call，将历史预算作为显式dataclass fixture、工作集及read_index原值注入；handler仅脚本响应usage0。每例要求所有任务/方案/状态/源码工作集/反馈/预算逐值还原，系统提示与全部schema相同，原50k/8k门禁通过，1脚本响应/0真实Token/未知0；失败保留并停止，后续未观察，不补例或改变旧raw。

编码只共享完全相同的dict/list，表存完整值，SHA核验；先还原原文本因子/共享文本，再JSON值。保留字段冲突、表篡改、含糊/悬空/嵌套引用及整体SHA错误均拒绝。无表示收益则保留旧表示，原工作集淘汰及模型/Token/费用/工具/命令限制不变。新增测试覆盖多轮实际图与不可压缩超限仍拒绝。

30例全部合格及独立逐值/大小/生命周期/来源/组件审计通过才允许准备独立新版本真实canary；不宣称30个新真实响应、完整任务通过、模型理解能力或前后工程版本因果增益。后续真实阶段仍须新独立身份绑定原用户10美元授权、扣除v2费用0.82323780美元及原绝对截止，SDK重试0、失败不补槽。
