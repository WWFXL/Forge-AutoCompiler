# H0/H1/H2 Runtime v6 正式比较预注册

## 身份与问题

- Identity：`cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v1`
- Tracking Issue：#453
- 研究问题：H2/Runtime v6 相对 H1/Runtime v4 是否严格成功非劣，以及 replay closure 与有界 submit-rejection
  recovery 是否在真实 Provider 轨迹中自然激活并减少不可复现候选。
- H0/Runtime v3 仅作为原始受限 ReAct 对照；H1 对 H0 是结构化 Harness 消融。

## 样本与调度

固定 `cmark@7e1e10c`、`mpc@1049534`、`expat@ac140c2`，每项目每 treatment 两次，共 18 arms。调度由 manifest
const 冻结并平衡 treatment 所处位置。旧 canary、资格和工程门禁 observation 不进入正式分母。

## Provider、预算与停止

使用 DeepSeek `deepseek-flash`，非流式、thinking 关闭、retry=0、timeout=300 秒。每臂最多 36 requests、600,000
recorded-token 下一请求阈值、100,000 单响应上界、700,000 authorized tokens、96 steps、72 tools、48 commands；
node/evaluator/replay 1800 秒，command 900 秒，cleanup 120 秒。全批上界为 648 requests、10,800,000 stop-threshold
tokens、12,600,000 authorized tokens 和 `$15.12`。

Q0 绑定 clean pushed release、父资格 evidence、source archive、image 和 Runtime v3/v4/v6。Q0 前禁止读取 credential
或调用 Provider。Evidence create-once；started 但无结果的 arm 不得 retry，失败与部分结果必须保留。identity、release、
source、image、runtime、预算、usage 或 credential 边界漂移时立即失败关闭。

## 主要分析

主要 estimand 为 `strict_success(H2) - strict_success(H1)`。按项目族有放回抽样 10,000 次，固定 seed
`45320261014`，取单侧 95% bootstrap 下界；非劣界 `-0.10`。正式执行只有在 18 arms 分类、请求与 usage 闭合、预算守恒、
source/post-action observation 绑定、treatment instrumentation 有效、cleanup 完成、无 infrastructure error 和批次预算未突破时
有效。

## 机制与次要指标

预注册报告 strict success、requests、input/output/recorded tokens、费用、墙钟、diagnostic commands、budget exhaustion、
no-candidate、S5 external replay failure、pre-freeze closure、submit rejection、repair window 打开/消费、repair action 完成和
二次 submit。构建系统分层只作描述。

H2 正向机制结论要求：主要非劣通过；H1 至少出现一次 post-freeze S5 replay failure；H2 至少出现一次 replay rejection，
并有 recovery window 打开和动作消费的可归因证据。若非劣通过但这些事件未出现，结论固定为“机制未自然激活”；不以
全成功替代机制证据，不进行阈值、样本、顺序或判据的结果后调整。

## 解释边界

三个项目族和两次重复只能支持固定样本上的有界机制复现。不得主张开放世界总体效果、统计显著性、通用模型排名，
也不得把费用或 Token 差异解释为动态预算控制效果。
