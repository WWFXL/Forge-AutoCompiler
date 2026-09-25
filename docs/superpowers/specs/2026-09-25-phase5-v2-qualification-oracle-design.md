# Phase 5 v2 资格门禁与 executable oracle 设计

日期：2026-09-25。追踪：Issue #294，关联 Issue #291。

## 1. 问题与证据

首次 Phase 5 已形成只读停止报告。新 identity 必须处理三个已观察问题，不能续跑、替换或回填旧 batch：

1. `c-ares@589b5887d47736e5b70a1fddaf9bf90297adde65` 的历史标签是 `autotools`，Forge 在 exact commit 上实际选择 `cmake`，旧 runner 在模型调用前停止。
2. `uwebsockets` 的 `HelloWorld` 是服务型 executable。外部 service oracle 已通过，但提交验证固定执行 `-version`、`--version`、`--help`，三个命令都会启动服务并等待产品默认超时。
3. `cppitertools` 和 `uwebsockets` 的 install 命令产生了候选未逐项声明的 support files。S2 把候选路径与 Session 完整交付集合强制等同，造成 `candidate_artifact_set_mismatch`。`yyjson` 和 `openh264` 的两个集合恰好相同，因此未暴露该问题。

## 2. 边界

本次实现产品验证合同和一个未授权的新 Phase 5 v2 candidate identity。开发、单元测试和 identity 生成必须保持 0 Provider、0 正式 attempt、0 新实验 evidence。首次 Phase 5 manifest、报告和 `.compile-sessions` evidence 均保持只读。

Stage C、公共 prompt、模型预算、停止规则和 Provider 配置不在本次范围内。

## 3. executable verification policy

`submit_build_result_impl` 新增可选的 `ExecutableVerificationPolicy`。policy 使用固定 schema version，并支持两种模式：

- `version_flags_v1`：默认模式，保持 `-version`、`--version`、`--help` 的现有产品行为。
- `successful_command_v1`：显式把 `/artifacts` 下的 executable 相对路径绑定到本 Session 内一条成功 `smoke` command ID。

`successful_command_v1` 采用 fail-closed 校验：绑定路径必须安全、唯一且实际分类为 executable；command 必须属于当前 Session、唯一、位于 supporting build 之后、role 为 `smoke`、未超时且 exit code 为 0。未知绑定、遗漏 executable 或非法 command 都使 candidate verification 失败。

提交验证不再次执行已成功的 oracle。它从权威 command record 和日志固化 `smoke_command`、`smoke_workdir`、exit code、输出预览与完整输出哈希。这样不会在同一容器内重复启动服务。

clean replay 继续运行 `repro/verify.sh` 中冻结的 verification command，并在 artifact comparison 阶段以相同 command 和 workdir 对 executable 做独立 smoke 比较。完整 artifact 集合、类型、大小、SHA-256、command、workdir、exit code 和完整输出哈希都必须匹配。为保持旧 Session 可读，新增持久化字段带 `None` 默认值。

外部 evaluator v2 只在以下条件全部成立时启用 `successful_command_v1`：S3 oracle 成功、目标合同只接受 executable、candidate 只有一个目标路径、oracle 只产生一个 verification command ID。其他情况继续使用默认 policy。该决策不按 task 名称硬编码。冻结的 evaluator v1 文件保持原字节与原规则摘要。

## 4. artifact 集合分层

S2 使用三个集合：

- `delivery manifest`：Session 中 `/artifacts` 下的全部文件，是 clean replay 的严格比较对象。
- `candidate declared artifacts`：模型在 `artifact_paths` 中声明的文件，必须全部出现在 delivery manifest。
- `target artifacts`：`target_mapping` 的值，必须属于候选声明，并满足 target ID、类型和路径 pattern。

允许 delivery manifest 含候选未逐项声明的 `support_file`。不允许未声明的 executable、library 或 object；此时仍返回 `candidate_artifact_set_mismatch`。所有 delivery manifest 条目仍必须有非空 size 和 SHA-256。该规则保留模型声明责任，同时允许成熟 install 流程交付 headers、许可证和 package metadata。

## 5. exact-commit build-system qualification

新 Phase 5 v2 candidate 不复用旧授权身份。每个 task 冻结：

- `build_system_capabilities`：在 exact commit 与冻结镜像中由 Forge 探测到的有序能力集合；
- `selected_build_system`：本 identity 实际要求 Agent 使用的能力，且必须属于 capabilities；
- qualification evidence 的 revision、image ID、task commit 与确定性摘要。

资格命令只做 clone、exact checkout、`inspect_build_system_impl`、持久化结果和 cleanup，不创建模型、不读取 Provider credential、不调用 evaluator、不创建 formal attempt。六个 task 全部成功且 0 managed orphan 后，qualification result 才可输入 candidate identity 生成。`c-ares` 的选择由该门禁结果决定，不能继续沿用历史 `autotools` 标签。

qualification 属于耗时 Docker 任务，由用户运行。开发提交只提供命令、schema、原子输出和校验器；qualification 结果回传前，v2 manifest 保持未冻结或不生成，不得授权 batch。

## 6. identity 与执行纪律

Phase 5 v2 使用新 schema/document type、独立 evidence 目录和新 attempt/thread 前缀。父级只引用首次 Phase 5 停止报告的 SHA-256 和 Issue #291/#294，不导入其 outcome 作为新 attempt。

新 runner 在模型创建前验证 release、qualification digest、六个 exact commit、capabilities、selected build system、镜像和 0 orphan。Node input 使用完整 `build_system_capabilities`，Session 使用冻结 `selected_build_system`。任何漂移均在 Provider 0 request 处停止。

## 7. 验收

- 默认提交路径的现有三旗标行为不变。
- 显式 oracle policy 在提交与 clean replay 中固定 command/workdir/result，非法绑定 fail closed。
- S2 允许额外 support files，拒绝缺失声明文件和额外 compiled artifacts。
- 快速单元测试、Ruff 与 identity 校验不访问 Provider 或 Docker。
- 用户运行 Docker qualification 和完整测试后，结果必须可由确定性校验器读取；在此之前不创建授权修订、不执行新 batch。
