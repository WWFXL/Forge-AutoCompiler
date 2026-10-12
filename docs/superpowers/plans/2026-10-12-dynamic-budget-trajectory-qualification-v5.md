# 动态预算轨迹 benchmark 资格 v5 实施计划

> Tracking Issue：[#427](https://github.com/WWFXL/Forge-AutoCompiler/issues/427)

## 目标

以全新 identity 完整重跑冻结的跨构建系统多步轨迹 schedule，并得到可审计的通过或停止结论。

## 实施步骤

1. 冻结 v5 manifest 和预注册，保持 v4 的 9 项目、动作、预算、停止规则与 Docker image 不变。
2. 新增薄 wrapper runner，继承 v4 的固定 hostname 和决策哈希语义，将 checkpoint 恢复接到 symlink-safe 恢复器。
3. 增加回归测试，验证新 identity/Issue、schedule 等价、零 Provider 边界和合法 libtool symlink 恢复。
4. 运行聚焦 pytest、Ruff、manifest validate/plan 和 Docker preflight。
5. 确认 evidence root 不存在、镜像 ID 匹配、受管容器为 0 后，执行唯一正式 `run`。
6. 执行独立 `audit` 与 `report`，核对 inventory、marker、result、54 个 continuation 结果和 cleanup。
7. 根据预注册门槛更新 `RESEARCH_STATUS.md`、工程交接和知识库固定路线；提交并创建堆叠 PR。

## 停止规则

正式 attempt 创建 evidence root 后不得重试或修补。任何新失败均保留原始证据并停止 Agent continuation/controller 设计；只有全部门槛通过才进入下一阶段设计。
