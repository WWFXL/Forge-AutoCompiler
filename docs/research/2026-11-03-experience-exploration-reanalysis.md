# E37规划探索补充分析

本次只读复用E37原48次轨迹，无新增Provider请求或构建，与原分母完全重叠。原始事实和费用仍以[原报告](2026-11-03-conditioned-experience-results.md)为准。派生结果为`benchmarks/analyses/cpp-build-evidence-conditioned-experience-flash-v1/task-exploration-reanalysis.json`，入口为`scripts/forge_analyze_action_experience.py`。

## 初始规划的探索成本

| E37处理 | 初始请求 | 源码读取 | 目录枚举 | 同任务内精确重复工具 | 初始输入Token | 初始输出Token |
|---|---:|---:|---:|---:|---:|---:|
| A无经验 | 66 | 53 | 37 | 11 | 1,042,179 | 50,865 |
| B旧结构化来源检索 | 53 | 46 | 29 | 5 | 966,234 | 45,362 |
| C新过程来源检索 | 66 | 63 | 30 | 7 | 1,263,917 | 68,581 |
| D同新库逐条选择 | 58 | 52 | 33 | 13 | 994,850 | 62,954 |

B相对A初始请求少19.7%、源码读取少13.2%，支持保留“某些经验能减少探索”的有利观察。C与A请求相同，源码读取多18.9%；更加详细的过程描述没有使本批初始规划少迭代。D的输入Token下降，输出仍更高；精确重复较多。数字为描述性计数，模型随机性、上下文内容与选择方式共同变化，不能把差异完全归于某一条经验。

恢复阶段A/B/C/D分别4/5/0/11请求，源码读取2/2/0/7次、失败日志读取1/2/0/3次。A恢复费仅占在线总费约8.95%（原报告），因此只优化恢复或追加难例，不能直接解决初始规划的主要开销。D的额外恢复不应统一归于经验负迁移：libsrtp检索为空、libsigcplusplus存在错误清理等案例须分别解释。

## 对下一阶段的影响

后续保留B作为实际有利的参照，以相同历史来源构造短动作经验，强调最小核对与优先动作，检验是否替代读取/判断。初始规划和每次恢复任务分别检索一次，任务内固定复用，动态状态不冻结。这个改动直接落实用户确认的阶段边界；它本身不保证少发Token，因为经验依然随模型上下文发送。

下一比较固定无经验/B旧经验/C短动作经验，所有组共用一次选择的任务边界。不能用新B与旧B的跨批差异估计快照因果，也不能将新三组视为仅改变单一字段。已有正负结果继续进入论文，当前分析不是新增效果实验。

## 计数定义与复现

按`agent.started`划分初始与恢复任务，按`model.request_started`绑定响应Token，按`tool.started`统计工具。精确重复限同一个Agent任务内的同工具、同参数；不同阶段重新读取不算重复。与原报告跨任务的重复定义不同，不能直接替换原数字。源码读取次数不等于读取文件数或语义冗余。

复现命令（输出须为不存在的新文件）：

```bash
PYTHONPATH=backend/packages/harness:scripts backend/.venv/bin/python \
  scripts/forge_analyze_action_experience.py \
  /home/yiwei/.codex/outputs/forge-evidence-conditioned-experience-flash-v1 \
  /tmp/forge-e37-task-exploration.json
```

原raw库存canonical SHA-256为`0af10f4cc4606fa0bba63d8a0f204179e61bfae13d4886c0aa402ce21696dbc0`；本次未修改raw或回填原缺失字段。
