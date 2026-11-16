# 构建Agent上下文容量修复与零Provider回放

本轮为工程修复，解决#801中恢复已核实依赖却无法继续请求的问题。未读取凭据或调用模型，不重跑旧身份，不修改论文或已有实验分母。

## 原因与修改

用户提供的官方DeepSeek Flash窗口为1M Token；49,000字节是本地人为限制。原恢复请求的系统提示、方案、交接、诊断记录和最新工具反馈叠加后，即使压缩仍触发本地停止，尚未到达Provider。此前另有工具定义8KB限制，且计量层保留单次100,000 Token上限；因此同时调整装配和预算，避免只扩大消息而与计量冲突。

当前`SimpleBuildMeter`覆盖的初始规划、恢复、强工具Agent统一使用：

- 输入工作预算64,000 Token，包含system、messages、普通工具及结构化输出定义。
- 复用已有tiktoken，以cl100k_base估算序列化输入，乘1.25并加2,048协议余量；该值不是DeepSeek精确Token数，不替代实际usage。
- 最多32,768 Token输出，若现有模型设置更小则沿用更小值；输入输出预留合计96,768，仍在单次100,000 Token计量上限内。
- 调用前验证窗口与计量配置，费用仍按单次100,000 Token和最高单价保守预留；完成后按Provider实际输入输出计费。
- 记录`model.context_budget`。超过工作预算仍执行有界压缩，保留任务、当前方案及最后失败命令；AI/Tool整体处理，不产生悬空调用。

诊断快照优先显示有核实记录的候选，最多六项，省略数量显式记录。搜索列表不再同时作为观察摘要重复展示；任务内候选和原始查询保持。快照不修改原内存。强工具基线同步容量规则与动态状态/最近反馈，但不接收Workflow的规划收敛指令；旧canary入口与冻结原件不变。

## 冻结失败材料回放

来源：`cpp-build-libffi-planning-dependency-flash-v1`，运行revision `0700a261cfb16b24b7bd4dfdb0bd05af8d16ebcc`；原件根目录：

`/home/yiwei/.codex/outputs/forge-libffi-planning-dependency-flash-2026-11-16-v1`

将已发送request8、随后保存的完整AI及两个Tool消息、八条真实查询按原顺序重组。它不是原本未发送request9的逐字副本。固定输入及SHA-256在[fixture](../../benchmarks/fixtures/recovery-context-capacity-v1/provenance.json)；脚本只重放记录，不执行查询、Docker或模型请求。

| 检查 | 旧实现 | 新实现 |
|---|---|---|
| 使用原件源码装配 | 请求前复现“公开任务与压缩后的必要证据超过规划上下文容量” | 送达脚本回执 |
| 全输入大小（含tools） | 旧规则下停止 | 51,995字节 |
| 估算Token／含余量预算 | 不适用 | 17,471／23,887，低于64,000 |
| 缺包证据 | 未送达下一请求 | libltdl-dev的installed=false保留 |
| 当前方案及最新AI/Tool组 | 原件保留 | 完整保留，无组压缩 |
| Provider调用／新增费用 | 0／0 | 0／0 |

[结果](../../benchmarks/analyses/request-context-capacity-repair-2026-11-16/result.json)及[原件清单](../../benchmarks/analyses/request-context-capacity-repair-2026-11-16/inventory.json)保存本轮回放。输出根目录为`/home/yiwei/.codex/outputs/forge-context-capacity-replay-2026-11-16-v1`。其中summary的model_requests=1表示计量中间件收到一次零Token脚本回执，实际Provider调用为0。

复现命令（从仓库根运行，输出目录需不存在）：

```bash
PYTHONPATH=backend/packages/harness python scripts/forge_request_capacity_replay.py \
  --output /tmp/forge-request-capacity-replay \
  --legacy-source /home/yiwei/.codex/outputs/forge-libffi-planning-dependency-flash-2026-11-16-v1/source-snapshot/backend/packages/harness/deerflow/compile
```

不指定`--legacy-source`也可运行新实现回放及固定输入哈希检查，无须历史源码或原输出目录。

## 验证与下一步

100项相关检查通过，覆盖上下文裁剪、诊断记录、环境查询、恢复装配、规划工具可用性和简洁构建；新容量用例覆盖系统提示与工具共同计入、输出上限、费用不足与不一致配置在调用前停止、强工具动态反馈和已核实候选优先。最终小范围复查与Ruff/格式检查通过。

本轮证明该冻结场景的本地容量阻塞已经解除，不能证明Flash必然提交正确安装方案，也没有新增libffi自主成功结果。下一步可在新身份与有效预算/时窗下做一次相同条件的自主观察，查看恢复是否依据证据生成安装指令、主构建及干净重建是否完成。
