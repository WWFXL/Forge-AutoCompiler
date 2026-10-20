# 三策略共同源码准备与完整执行资格：结果及未观察边界

本轮是基础设施与工程资格，解决三策略获得相同来源索引、共同装配及空环境重放的问题。没有真实Provider效果数据，不估自然成功率、成本优势或方法排名。主线及硕士目标保持；不加P2、不改RQ3固定分母，不为取得正结果改变最终裁判。

独立`cpp-build-cxx-common-input-gate-v3`观察10槽、10槽strict，snappy强工具槽因启动前剩余时间不足2100秒而未观察。**11槽完整资格尚未完成，不能直接启动18槽付费比较。** v1/v2失败永久保留，不与v3拼接成11/11。Issue #556保持OPEN，代码和部分资格结果可在最终HEAD三CI成功后合科研依赖分支，未合main。

| 固定路径 | 工具规划Workflow | 模型规划Workflow | 强工具Agent |
| --- | --- | --- | --- |
| buffer受控build失败恢复 | strict，一次交接/修订 | strict，一次交接/修订 | 本协议无此槽 |
| yaml-cpp正常 | strict | strict | strict |
| simdutf正常 | strict，0脚本模型请求 | strict | strict |
| snappy正常 | strict | strict | 未观察：启动余量不足 |

## 实现与完成证据

所有方法在首次模板/Agent操作前共同执行受计量dependency命令：临时容器内确切`/workspace/repo`建立Git索引并验证原文件集合，不伪造commit或完整历史。Workflow绑定已成功的命令身份、不重复执行准备；强工具自动成功配方包含同一准备记录。空环境replay从归档源码重新执行准备，不复制原工作区`.git`。只保证原文件内容与索引文件集合，不主张Git完整对象或历史恢复。

CMake任务检查真实布尔含义，保留必要功能及完整作者测试；等价OFF/FALSE/0不因缓存类型被拒绝。未显式出现的BUILD_SHARED_LIBS按默认静态，仍须真实ar精确交付。完整CTest输出JUnit后检查固定3/94/1项实际执行、0skip/0fail/0error，前后核对索引。yaml-cpp原/replay各1068默认GoogleTest通过、CTest3/3；snappy各25默认GoogleTest、CTest1/1。上游8/1默认DISABLED保留，不填通过。simdutf原/replay各94/94实际Passed，宏检查实际执行，0skip。

v1发现yaml-cpp上游测试复制同名静态库。新暂存器仅把同名、相同size/SHA256及完整权限模式的安全ELF/ar副本视作一个交付身份，确定性选择排序首路径。不同内容/模式、越界、悬空、循环和缺失仍拒绝；不降低最终精确路径集合/类型/内容hash/replay标准。新装配与恢复合同共同引用这一暂存器，两Workflow不能自行替换固定测试/暂存；强工具仍作为整策略参照。

两条受控恢复各真实build失败一次、handoff一次、revision2；共同准备与成功configure原命令ID保持，失败build命令后缀改写后重新执行。最终replay从空源码完整执行配方，不复用原构建文件。只证明该受控路径的接线，不估自然恢复率或最小修订收益。

## 停止身份与失败证据

| 身份 | 运行release | 观察及停止 | inventory SHA256 |
| --- | --- | --- | --- |
| common-input-gate-v1 | `8884314ec6b081283d8889da6f8a9e09c6f16de4` | buffer2strict；yaml完整测试后同名副本暂存拒绝，恢复材料>50k、无新请求；8未观察 | `7c4a2a1fe2d7912d7a58d84a52df61471d0f63e5d0fb066a7deec1e3ed01d7a0` |
| common-input-gate-v2 | `7ed4731f1870c5d9cb5ca291624de4a2d8870fde` | 首buffer失败后旧恢复合同拒绝新stage，首次模型前停止；10未观察 | `9ba4e638105a1bc98ca83dff135aea975fdfa443fe5a4023ac79c82f77f9a573` |
| common-input-gate-v3 | `828b4504127370d078e262a4e4c0210370bfecb3` | 10strict；最后snappy强工具启动余量不足，1未观察 | `41ec832da84f1ca2ec69d374f30182f89354c8747c28f380697ce8ca8cbc9ecf` |

v2是本轮工程接线缺陷，不是模型恢复失败。v3原runner的`stop_reason`写为`initialization_not_completed`，细分原因由原启动日志中`before_deadline(...,2100)`异常确认；不回写raw字段。v3唯一启动2026-10-20T17:09:03.036864+00:00，最后槽准入在UTC17:44:33之后，按原绝对截止UTC2026-10-20T18:19:33Z保留清理余量。没有续跑或扩时。v1的50k恢复材料限制仍保留，未通过本轮关闭门禁或扩额解决，不称所有复杂恢复已合格。

v3 manifest SHA `af7be3c3eb9be2da8a10bfdce7efc6c371b8a0d6245b130fd84fc7f9aec17c96`、157组件；逐级保留原141/148/152组件。封存30910普通文件、6链接、1097122362bytes。10脚本响应、59受计量原执行命令、累计臂秒2146.0354（包括准备、完整验证、replay、cleanup），真实Provider/凭据读取/模型Token/模型费用/未知用量均0。Fake请求不解释为真实模型请求收益。

## 独立核验与工程检查

不导入Forge的stdlib审计逐文件复算typed inventory/seal、父证据、组件快照、来源归档、原/replay源码hash、索引文件集合/no HEAD、准备唯一性及时序、完整CTest日志/JUnit、精确ar/ELF交付及replay内容hash、两恢复成功前缀/失败后缀与固定任务、原/replay镜像2CPU、实际Docker容器不存在，`valid=true`。第二份独立审计直接解析原/replay实际CMakeCache及脚本模型原响应，验证功能配置、零Token、准备计量与包含replay的总臂时间，`valid=true`。两旧失败身份各自独立审计通过，原源码及cleanup保持。

新增30项相关回归、产品2188passed/44skipped/27warnings、Ruff/570文件格式及实际CLI预检通过。最初Shell转义测试、宿主Python3.10不支持file_digest、审计器将list响应误作dict等失败日志均保留，修复后相应检查通过；不计为策略效果。历史pytest临时目录权限清理告警保留、不清除其他任务目录。v3运行release三CI已通过，发布仍须最终报告HEAD三CI；具体PR/merge以GitHub及最终发布收据为准。

## 证据位置及下一步

仓库协议：`benchmarks/{manifests,preregistrations}/cpp-build-cxx-common-input-gate-v{1,2,3}.*`。
raw：`/home/yiwei/.codex/outputs/forge-cxx-common-input-gate-v{1,2,3}/`，均永久只读。
会话收据：`/home/yiwei/.codex/outputs/forge-cxx-common-input-session-2026-10-21/`，包括唯一启动、终态、derived-summary、v1/v2失败审计、v3-independent-audit、v3-completion-independent-audit、测试/lint/CI/发布和知识库收据。知识库真源仅MCP维护，不复制Vault正文或注入实验Agent。

下一项是在新有效免费运行窗口、独立新身份下补snappy强工具共同准备/完整测试/精确交付/clean replay/cleanup资格，不续跑v3；其后再冻结18槽真实比较的入口、前瞻暴露、六排列平衡、完整费用计量和有效新预算/时窗。旧#552付费stage不续用。全部三项为已见CMake C++、yaml/snappy共享GoogleTest，不当完全holdout、三个独立统计家族或跨系统/大型C++泛化。保留小幅或条件性收益与成本/时间取舍的研究价值。
