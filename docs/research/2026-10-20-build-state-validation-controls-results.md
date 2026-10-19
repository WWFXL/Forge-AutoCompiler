# 状态变化与分层验证控制结果

## 身份与完整性

跟踪#498；独立身份`cpp-build-state-validation-controls-v1`，运行release `1052766e6e1712ddee9f1db90bec3fc1d302ded3`。七槽各一次、无替换/重试，0Provider/0模型费用；没有修改旧冻结证据。协议见同名manifest/preregistration。

原始证据`/home/yiwei/.codex/outputs/forge-build-state-controls-v1/`，2458普通文件、21链接、63,414,830 bytes；typed inventory canonical SHA-256 `f013a79451c2630f0ffd8e532eacda46a371716d1397eb500eaca5cc1f51cc85`。独立审计位于`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/state-controls-v1-{integrity,outcome}-audit.json`，两者valid=true。组件快照、全部文件/链接、原始源码和具体拒绝原因均核对通过；七槽cleanup成功，对应容器0残留。

## 观察

| 槽位 | 实际观察 | 预定原因成立 |
| --- | --- | --- |
| miniz正常 | 完整测试、精确交付、clean replay，Session completed | 是 |
| miniz空测试 | CTest exit0，实际No tests were found!!!，固定check输出义务不满足，needs_handoff | 是 |
| pigz正常 | 完整测试、精确交付、clean replay，Session completed | 是 |
| pigz交付漂移 | 原完整测试通过，追加固定字节后仍是ELF且smoke匹配；replay size_mismatch，大小及SHA不一致 | 是 |
| libite正常 | 完整测试、精确交付、clean replay，Session completed | 是 |
| libite遗漏bootstrap | 工作容器全部21测试通过；候选遗漏bootstrap，空源码replay的./configure不存在、exit127，recipe_execution_failed | 是 |
| miniz外部configure | 另一执行方真实关闭测试并追加权威configure；旧Workflow以PlanContractError停止，0 replay | 是 |

三个正常严格完成、四个负控制按预定原因拒绝，合计7/7预期观察成立。这不是七个构建全部成功；负例Session按协议失败收尾并保留。

## 解释与下一步

完整测试检查能区分exit0与真正执行测试；精确交付比较能发现类型和版本smoke均正常的漂移；clean replay能发现工作区已生成但配方未声明的bootstrap依赖；命令frontier保护能拒绝外部命令后过期的执行状态。最后一项只覆盖权威记录变化，不代表可发现任意无记录文件改动。

这些结果支持已有合理规则和分层验证对四类已知、受控缺口的开发资格。没有调用Agent修复，没有证明状态选择增量、自然失败恢复率、自然误接受率或总体成功率。不能因为预期控制通过就增设复杂P2；后续保留本规则强基线，先完成两项Make参考资格，再执行独立前瞻性双臂比较。

本阶段实现的10项相关回归、默认产品1905 passed/44 skipped及Ruff已通过；本次只补充结果解释和状态入口。原始证据不变。
