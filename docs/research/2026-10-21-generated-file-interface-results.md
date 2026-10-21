# 生成文件边界 B：共同执行接口与真实项目资格

2026-10-21，Issue #575。基础设施实现及工程资格完成；解除标准 Autotools 生成模板与原文件保护之间的冲突，供下一轮公平比较共用。主线、完整作者测试、功能配置、精确交付及 clean replay 保持。

## 结果与解释

| 新身份 | 正常三策略 | 受控 Workflow 恢复 | 未观察 | 结论 |
| --- | --- | --- | --- | --- |
| `cpp-build-generated-file-boundary-gate-v1` | 3/3 严格完成 | 工具来源首次恢复在模型前被交接身份校验拒绝 | 模型来源恢复 1 槽 | 完整资格未通过，失败封存 |
| `cpp-build-generated-file-boundary-gate-v2` | 3/3 严格完成 | 两来源 2/2 严格完成 | 0 | 独立完整五槽资格通过 |

三策略是工具规划 Workflow、模型规划 Workflow、强工具 Agent。全部模型响应由脚本提供，不连接 Provider；v1 四次、v2 七次脚本响应、零模型 Token/费用/未知用量。v2 共 32 条受计量原执行命令。不能把脚本响应数当真实模型请求节约或方法效果。

v1 的拒绝源于顶层交接使用可读计划 SHA，而状态内交接仍引用包装计划 SHA。v2 同时可逆投影状态、交接和当前计划，另外保留并核验 `guarded_plan_sha256`，权威持久化记录不改，原身份校验不删除。新身份完整重做五槽，未拼接旧成功槽。

v2 两次恢复实际先执行 `build=false` 并得到 exit 1，再由脚本响应修订编译动作；都只有一次 handoff、最终 revision 2。已成功的源码准备、依赖生成、configure 三条命令 ID 保留，从 build 重新执行后续测试和暂存，失败命令不进入成功配方。这里只验证受控后缀恢复，不估自然失败率或节省幅度。

## 共用任务与实现

固定 `hyperrealm/libconfig@a42cb47c1526a4f2ed025fcbb2289863375bc898`，原归档 SHA `8309753e981287e91279903bc5d126c152e846e2770ed2174239129ca2f20224`、原不可变 GCC13 镜像、2 CPU。开发助手此前已见项目、参考运行和输出，不能称前瞻样本或 holdout。

原归档 265 个普通文件，264 个默认保护；仅允许已有 `ac_config.h.in` 由精确命令 `AUTOHEADER=true autoreconf -i && autoheader --force` 更新。上游 `configure.ac` 的 `AC_CONFIG_HEADERS(ac_config.h)` 与模板 autoheader 来源声明，以及同镜像独立生成审阅共同支持此权限。新文件的 111 条精确路径及缓存/对象目录来自已见成功开发参考，明确不是新项目通用白名单。

模板从 `e284232a0c5b90dda4967791cf232c4e723e20fc0afd9c86842639237297c81d` 更新为预先独立核验的 `e42059a908f1eeb0ed9ea8cc5d3dd3343f029a441b70967f0857ae1c8a21a486`。作者源码、测试、configure.ac、Makefile.am、手写宏等均不获写权限，恢复 Agent 不能扩展边界。

`generated_file_boundary.py` 冻结路径、生成命令、工作目录、输入关系及预先核验的输出哈希；`boundary_execution.py` 为两类执行服务接入同一包装。原执行和 replay 使用完全相同的实际包装命令。可读状态只可逆还原命令，不用模型总结替换原始日志。新 runner 独立于旧冻结入口；v2 入口修复可读身份投影。

Linux 文件事件结合内容、inode、ctime 和模式检查识别受保护文件先改后恢复、替换及祖先目录移动；不可用或队列溢出拒绝。非声明命令即使写出正确生成哈希也拒绝。初始归档链接当前不接纳，新输出链接仅允许指向仓库内新增普通输出。不是恶意 root 进程的通用安全沙箱，也没有证明所有系统路径、进程或环境隔离。它是执行后任务违规识别，并不预先阻止所有副作用。

## 独立核验

独立 stdlib 审计未复用 run_arm 或 strict 分类器，重建类型化清单，解析实际命令 AST 中的边界代码和载荷，核对日志、原执行与 replay 文件及产物。v1、v2 均 `valid=true`；失败身份被准确保留。

v2 五槽每次原执行及重放均满足：

- 264 个受保护文件 SHA 不变；生成模板为声明的新 SHA，日志记录前后变化。
- 原完整 Automake 测试结果精确为 8 PASS + 1 上游预期 XFAIL；内层 tinytest 16/16，未把 XFAIL 改填 PASS。
- C++、tests、examples、static 开启，shared/doc 的原任务配置保持；不是临时减少测试义务。
- 精确交付 `libconfig.a`、`libconfig++.a`，原/replay 集合、结构、大小及 SHA 一致。
- 原容器与重放容器记录 ID/名称均在实际 Docker 列表中不存在，cleanup 成功。

29 项新增相关回归通过；最终产品测试 2316 passed、44 skipped、27 warnings，backend lint/format 与四个执行脚本 Ruff 均通过。封存后仅将新增回归测试的审阅收据改用临时文件，消除 CI 对本机私有路径的依赖；没有修改实验运行时、任务、manifest 或 raw。差异由 `test-portability-revision.json` 记录。v2 原 203 组件的准确版本在 raw `source-snapshot/`，复现历史身份应使用该快照；不能将后续测试可移植性修订冒充运行前版本。

## 证据指针

运行前 checkout 基线为 `14c563b11e6e02339a20727045b256f531452dd4`，新实现当时未提交；该基线本身不包含新代码。manifest 的逐组件 SHA 与封存的实际 `source-snapshot/` 定义运行实现，后续发布 commit 定义代码发布状态。

| 身份 | manifest SHA | inventory SHA |
| --- | --- | --- |
| v1 | `017043e7b765045eff5d3fe0a762ea4a201aa0f1dfbc1c43a8545861559ab202` | `b712244558525d077221a0e3c5e38c381b60ee00c5951b26389c02078f339136` |
| v2 | `9be86a5794300a9360f451b22de2a5847268fb5480278d84d79d5ea21475001f` | `4a345e396f5b3b1308376fbdabb71f831661f81d135da91d41fed9214d1cca93` |

- manifest/preregistration：`benchmarks/{manifests,preregistrations}/cpp-build-generated-file-boundary-gate-v{1,2}.{json,md}`。
- 版本化派生结果：`benchmarks/analyses/cpp-build-generated-file-boundary-qualification-results.json`。
- raw：`/home/yiwei/.codex/outputs/forge-generated-file-boundary-gate-v1/`（5054 文件、12 链接、185733894 bytes）及 `forge-generated-file-boundary-gate-v2/`（7272 文件、20 链接、275813150 bytes）。
- 源审阅、独立审计实现/结果、检查日志及发布收据：`/home/yiwei/.codex/outputs/forge-boundary-interface-session-2026-10-21/`。

审计初版误从原始 session 命令读取仅投影记录才有的 log_sha256，在输出报告前失败；改为直接对封存 inventory 核对日志哈希后两身份通过。产品测试首次有历史 pytest 临时目录权限清理告警，最终检查使用新 basetemp；不清理无关用户目录。

## 下一阶段与主张边界

可以在新任务边界下准备独立任务资格、固定策略比较；三策略统一使用该边界，不能把共同任务定义变化算成某种规划收益。新的项目须重新审阅生成来源/精确权限，不复制 libconfig 的输出列表作通用授权。样本暴露和选择依据在结果前登记，接受小幅或有取舍的真实收益。

本轮没有新增真实模型效果，不回填旧 libconfig 九槽、不改 RQ3 旧分母、不加 P2、不换主线；也未证明两个创新点已经成立。旧 20 美元/四小时时窗不续用，本次费用为零。下一轮付费比较须先有具体冻结身份与新的有效费用和运行窗口授权。
