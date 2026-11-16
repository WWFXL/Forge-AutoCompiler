# 恢复Agent的容器搜索与依赖查询修复

日期：2026-11-16；Issue #760。类型：工程修复，0真实Provider调用、0新增模型费用。用户批准修复，本轮不修改论文和旧实验结果。

## 修复内容

上次libffi观察中，恢复Agent的111次工具调用只有源码、目录和日志读取，不能搜索容器安装的开发文件或查询软件包。此次在简洁构建入口的恢复交接中增加两类结构化工具：

| 工具 | 实际能力 |
|---|---|
| `search_build_files` | 项目、系统宏、头文件、pkgconfig或受管外部依赖的固定文本搜索，返回文件、行号与片段 |
| `inspect_build_environment` | 构建工具版本/路径，包状态/候选/文件/所属包，包名/文件索引，搜索路径与指定开发环境变量 |

通用指导要求从日志缺失名称出发，核实提供者、安装状态和路径，再决定最小修复。空结果不等于功能被版本移除，不伪造宏。提示与工具实现不含libffi、具体宏名或包名答案；具体答案仅在明确预写的工程脚本中。

查询使用已有runtime和会话记录，受原任务预算及每次交接12次上限约束；不执行模型提供的任意Shell，不安装、不推进阶段。命令标记为`diagnostic`并同步frontier，不进入成功配方。修复仍返回完整方案，由Workflow执行。初始规划、强工具Agent和产品Lead/compiler入口不随之修改。

新增指导在P0/R2原底座指纹校验后追加，原R2候选保持；查询重复判断忽略新日志/命令ID。旧冻结入口及运行仍按原revision解释。

## 真实容器验证

同E57 libffi原源码/镜像、原初始方案，在真实容器执行缺宏失败，通过真实Agent图调用7次查询，最后由脚本提交已知系统开发包修复。实际证据为：

1. 项目搜索定位`configure.ac:219`的`LT_SYS_SYMBOL_USCORE`调用；系统aclocal目录中无定义。
2. 命令查询返回aclocal 1.16.5及程序路径；默认宏目录为`/usr/share/aclocal`。
3. 包查询返回`libltdl-dev`状态`un`，最终工具明确`installed=false`；包名检索`ltdl`返回该开发包候选。
4. `apt-file`未安装，文件索引查询返回`unavailable`；未安装/刷新索引，不能声称可自动查出任意缺失文件的提供包。
5. 预写方案增加`apt-get install ... libltdl-dev`。Workflow保留成功工具安装，清理生成物，再执行原autogen/configure和make。原失败保留，7条诊断不进入实际成功重建配方。

| 工程路径 | 目的 | 结果 |
|---|---|---|
| `cpp-build-recovery-environment-tools-repair-v1` | 首次工具接线，未附R2候选 | 主构建、静态/共享交付、实际重建、源码保护和清理通过；76.08秒 |
| `cpp-build-recovery-environment-r2-repair-v1` | 最终状态/路径输出、进展判断及P0＋原R2兼容 | 同上全部通过；75.12秒 |

两条均为8次脚本回复、7次真实查询，Provider/Token/费用均为0，不是自主模型试验。第二条为修改后兼容性验证，不替换首条。每条2个容器、4个名称/ID实查不存在；不回填旧失败或增加E57效果分母。

## 检查与结论

15项新工具/接线检查及相邻现有规划、Workflow、runtime检查共207项通过，相关Ruff和Git差异检查通过。覆盖真实搜索、输入/越界拒绝、搜索截断、包和索引不可用、预算、过期交接、原失败保留、真实Agent图反馈、P0/R2提示兼容及诊断不进入配方。

已证明恢复Agent能获取原先缺失的环境证据，并在查询后交还Workflow。尚未验证Flash会自主选择查询、找到正确包或降低恢复费用。下一步可在独立身份中，不给包名与修复方案，观察最终接线的自主诊断轨迹；正式比较和入文仍由用户决定。

## 证据指针

- 最终入口：`scripts/forge_recovery_environment_repair.py`；[执行契约](../compile_workflow_execution.md)。
- 首次原件：`/home/yiwei/.codex/outputs/forge-recovery-environment-tools-repair-2026-11-16-v1`；`summary.json` SHA-256：`9062ac177823b19574d6d6aa5da7499c36c7935b8fbdcec716dd338e9a3c2dad`。
- 最终原件：`/home/yiwei/.codex/outputs/forge-recovery-environment-r2-repair-2026-11-16-v1`；`summary.json` SHA-256：`e8d546c61b85461f77fa5eb28dccffd4fd908524f19c70758ed5d3d626d93a65`。
- 每目录保存`scope.json`、`case.json`、`source-snapshot/`、`source-sha256.json`、`summary.json`、`completed.json`与`cleanup-inspection.json`。`libffi/agent/`保留请求/响应和查询事件，session保存命令日志、修订、交付与replay原件。各源码快照对应实际运行版本，不用最终文件覆盖首条快照。
- 发布状态以Issue760关联PR最新HEAD、CI及科研集成分支合并记录为准。
