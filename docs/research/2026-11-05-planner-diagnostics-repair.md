# 简洁规划诊断元数据修复

2026-11-05，Issue #689。本轮是工程修复，真实 Provider 请求及新增模型费用均为 0，不是新的方法效果比较。

E47 的 highwayhash 基础组已生成 `make -j2`，但 `diagnostic_paths` 先填写 `/workspace/repo`、后改成 `.`，两次均因诊断路径校验被拒绝，构建未启动。原响应和失败结果完整保留。

## 实现

从 `SimpleBuildAction` 的模型 schema 移除 `diagnostic_paths`。若响应仍包含这一非执行提示，仅丢弃该字段，不解释、读取或执行其路径；原响应由已有计量器原样保存。其余未知字段、动作依赖、执行目录和严格 Shell 检查保持。规划提示词与恢复上下文同步移出诊断采集职责。

系统原有的命令完整日志、退出码、失败日志哈希与输出尾部仍进入恢复交接；本次没有新增项目专用规则或目录遍历。通用 `PlanStep` 及旧观察接口的诊断路径校验不改，独立测试、交付和重放检查不变。

## 验证

- 修复前针对性回归重现 schema 暴露、原响应被拒绝和恢复上下文携带诊断字段；修复后三个直接相关测试文件共 56 项通过，Ruff 与格式检查通过。
- 原两份工具参数分别通过工具输出和正文 JSON 接收，共四条真实 Agent 图离线回归；各一次脚本响应即可交付，命令不变，诊断字段不进入动作，原响应保留。夹具见 `benchmarks/fixtures/simple-planner-diagnostics-v1.json`，记录来源响应 SHA-256，不包含模型内部推理。
- 越界工作目录、路径穿越、其他未知字段继续拒绝；真实 `make missing-target` 失败保留退出码、日志和交接，修订后继续可构建。
- 使用第一份原响应原样参数进行一次独立的零 Provider highwayhash Docker 工程实跑：原源码构建、`highwayhash_test` / `vector_test` / `sip_hash_test`、交付、干净重放及清理全部通过，源码未改，总计 23.06 秒。一条零 Token 脚本模型响应不计真实模型效果。

工程原件：`/home/yiwei/.codex/outputs/forge-planner-diagnostics-repair-2026-11-05-v1/`。`scope.json` 和 `source-snapshot/` 固定运行时修改，`engineering-result.json` 为实际构建结果，`verification.json` 保存只读核对和容器不存在检查。驱动在结果保存后误读 `model_usage` 而退出；正确字段为 `agent_usage`，随后只读核对通过，原脚本与错误日志保留，没有重跑构建。

本修复不回填 E47 成功，不重跑旧 manifest，不推断模型成功率提升。跨项目检索、两层经验联合比较及新付费实验不在本轮范围；后续比较需使用修复后的独立运行版本。
