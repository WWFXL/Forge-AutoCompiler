# 进展感知结构化 Agent Harness 资格 v2 实施计划

1. 保持 v1 raw evidence、inventory、report、runner 和 manifest 只读，并绑定 v1 失败 inventory。
2. 冻结 v2 manifest、Schema、预注册、组件哈希和 source-ready archive SHA-256。
3. 在恢复 state-3 工作 checkpoint 后，把 state-1 source archive 复制到新 Session repro 目录并绑定身份。
4. 使用与 v1 相同的本地脚本模型运行 configure、build、artifact-stage、ready guard 探针和快照提交。
5. 运行 pre-freeze verifier、external evaluator S0-S5、functional oracle、离线 clean replay 和 cleanup。
6. 审计 0 credential、0 Provider、预算计数、H1 事件、source snapshot、无 `git fetch` 和父 evidence 不变。
7. 通过则只进入 H0/H1 Provider 配对实验设计；失败则停止 Provider 比较并保留完整负结果。
8. 更新研究状态、提交报告并推送堆叠分支；不自动创建 Provider identity 或调用 Provider。
