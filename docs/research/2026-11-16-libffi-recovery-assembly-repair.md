# libffi恢复方案装配修复与真实构建

日期：2026-11-16；Issue #754。类型：共同工程修复与针对性验证，0真实Provider调用、0新增费用，不增加模型效果分母。

## 问题与修复

E57/B的libffi首先在`autogen.sh`遇到`LT_SYS_SYMBOL_USCORE`未定义。其最后恢复响应还暴露两处共同接口问题：第一次步骤标识包含版本号点号，被格式校验拒绝；纠正命名后仍引用已经成功的`install-autotools`，但旧校验要求引用先出现在本次返回列表，早于执行器保留成功依赖的装配，因而再次拒绝。

本轮在`simple_build_task.py`修复：

- 只将步骤标识中的`.`转换为`_`，同步本方案`requires`引用；规范化冲突继续拒绝。命令、工作目录与实际动作不改变，原响应仍由ledger保存。
- 为当前恢复交接建立局部结构化Schema；从当前方案及系统交接记录取出真实成功依赖，核对ID、命令、工作目录和非空命令ID，在完整图校验前补回遗漏步骤。类按调用隔离，不共享全局状态；JSON正文和工具输出使用同一路径。
- 保持未知引用、前向引用、重复标识、明确弃用后仍引用、隐式覆盖成功依赖、无实际动作变化及原源码保护等拒绝。成功依赖的执行/重放权威仍由Workflow核验，不由模型声明。没有放开全局排序或自动执行任意删除。

## 工具链原因：缺少宏开发包，无需降级

原镜像Libtool为`2.4.7-7build1`，没有`/usr/share/aclocal/ltdl.m4`。本轮检查GNU发行材料后，进一步在实际构建容器中安装`libltdl-dev`并记录：

```text
libltdl-dev:amd64  2.4.7-7build1
libtool           2.4.7-7build1
libltdl-dev:amd64: /usr/share/aclocal/ltdl.m4
757:AC_DEFUN([LT_SYS_SYMBOL_USCORE],
```

补齐该包后原autogen/configure流程成功。这推翻了旧恢复响应中“Libtool 2.4.7已移除该宏、必须降级2.4.6”的未经验证判断：宏实际属于ltdl宏文件，缺的是相应开发包。未修改`configure.ac`，未添加空宏，未改变作者默认主目标，也未给系统添加libffi专用自动降级规则。

前置诊断从USTC获取GNU发行包遇到HTTP403，改从GNU取得材料；该读取不是构建实验重试。正式工程路径没有下载或编译旧Libtool。

## 单条真实工程路径

身份`cpp-build-libffi-recovery-assembly-repair-v1`；用户授权本轮修复，0美元/0Provider，单路径，非预期失败停止，不自动重试。沿用E57同commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`、同源码归档与镜像；只读旧证据。

执行入口：[forge_libffi_recovery_assembly_repair.py](../../scripts/forge_libffi_recovery_assembly_repair.py)。先执行E57/B原初始方案，实际复现同一宏错误，再由真实Agent图接收一次预写脚本响应：新增`libltdl-dev`安装，引用但不重复提供旧成功的`install-autotools`；新ID `install-ltdl.1`实际规范化为`install-ltdl_1`。Workflow保留成功安装记录，清理失效生成物、执行新增依赖、重新配置并编译，随后完成交付和全新容器重建。

| 观察项 | 结果 |
|---|---|
| 原始autogen失败 | 实际复现，退出1及相同宏错误 |
| 补齐宏开发包后的配置/主构建 | 通过/通过 |
| 主要库交付 | libffi静态库及共享库，通过 |
| 同镜像干净重建 | 实际执行并通过 |
| 原源码与测试保护 | 通过，0原文件改动 |
| 完整作者测试/可执行入口 | 不要求/库不适用，不填测试通过 |
| 清理 | 构建及重建容器的4个名称/ID引用均确认不存在 |
| 总路径耗时 | 74.43秒，包含原失败、恢复、交付与重建 |
| 在线模型 | 0真实请求；1次离线脚本响应，0Token、0美元 |

原始目录`/home/yiwei/.codex/outputs/forge-libffi-recovery-assembly-repair-2026-11-16-v1`：scope/case、运行源码快照与哈希、逐命令日志、原失败、原响应/装配方案、session、replay和清理确认均保留。[摘要](../../benchmarks/analyses/libffi-recovery-assembly-repair-2026-11-16/summary.json)SHA-256为`b591dd89361f0584ea012528f9b1e75ea64e6471d55f6653c9a4e69851e72c6c`；脚本在采集后的唯一变动为格式化，运行原文在source-snapshot保留。

## 检查、结论与下一步

77项相关回归通过（简洁构建、结构化规划、成功依赖保留及共同恢复）；新增3项包含真实Agent图＋本地实际编译、规范化冲突及错误引用拒绝。Ruff检查/格式与diff检查通过。另5项E57历史入口回归通过：首次CI的两项失败来自旧协议组件哈希与当前源码不匹配，测试改为在真实历史revision文件上验证；正式入口及冻结manifest不改。没有为了写报告运行本地产品全测。

本轮证明：补齐ltdl开发宏能解决固定libffi版本的此次准备失败；修复后的接口允许恢复方案正确引用历史成功依赖并完成真实构建与重建。不证明Flash会自主提出该正确修复，也不把工程路径算成R2相对H0的效果。

E57五个未完成槽与10/12、11/12、10/12保持，论文不回填。到此结束修复阶段；下一研究仍是确定配置在新项目上的综合评价，付费运行需单独协议与有效授权。11月14日v0.12本地论文润色稿在另一工作树，保持原样。
