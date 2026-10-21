# #587 共同资格资源说明勘误

冻结的 cpp-build-rtorrent-common-entry-gate-v1 preregistration将“原12请求、150000累计Token停止阈值、单响应50000”误写为最早 trial_budget 的数值。该文字不符合本轮冻结共同计量器源码：CanaryMeter 覆盖为累计400000、单响应100000、72 Agent steps、48 tool calls；12请求与32命令保持。实际首个请求 remaining_budget 已显示400000 Token、12请求、72 steps和48 tools，源码快照和组件SHA均在运行前冻结。

本说明保留原协议与证据，不修改已冻结文件，不将旧文字当新阈值。资格全程禁止Provider、凭据和真实Token，实际模型费用为0；该笔误没有放行任何付费支出或模型Token。只能按实际冻结实现报告工程资格，不声称核验过150000/50000配置。后续独立真实canary候选明确绑定400000/100000及500000每臂设计授权上界；不得用本说明给旧身份续跑、回填或放宽成功判定。
