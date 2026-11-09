# 配置阶段执行与实际状态观察修复

2026-11-09，Issue #701。本轮是共同执行底座的工程修复，真实 Provider 请求、Token 和新增模型费用均为0；没有新增 Harness 效果比较。

## 修复内容

E51的miniz槽15中，`cmake --preset gcc`已生成`build`目录，观察器却查仓库根；libogg槽6/18中，单独执行的`autogen.sh`成功后，被提前要求配置已经完成。三个原未完成结果保持，不改为成功。

- CMake配置动作优先使用**本次命令日志**中CMake报告的实际输出目录；由CMake自己解析preset的继承和宏，不手工解释preset文件。日志只定位目录，真实Cache的源码身份、缓存目录、generator及构建入口仍须通过检查。build动作按自身目录观察，不借用旧配置日志；越出仓库的路径拒绝。
- 配置阶段可以有多个动作。中间动作正常退出即完成该动作，实际配置状态仍如实记录为unknown/passed等，并标记`phase_complete=false`；最后一个配置动作执行后才要求最终配置状态成立。没有按autogen脚本名或项目名放行，所有中间命令失败仍立即交接。
- 最终配置缺失的交接原因改为`configuration_state_incomplete`，保留真实退出码、日志和配置状态，避免将状态观察问题笼统描述为命令失败。恢复的无变化修订保护保留。

模型/提示、工具、规则、任务、源码/测试保护与独立主产物、精确交付和干净重放均未改；H0/H1共同使用该修复。

## 两条实际构建

沿用E51原始初始方案的命令、顺序和工作目录，从固定源码及同一镜像启动新会话。未调用规划/恢复模型，也没有合并或替换原指令。

| 工程路径 | 执行命令 | 主构建 | 精确交付/干净重放 | 源码/清理 | 全流程秒 |
| --- | --- | --- | --- | --- | --- |
| miniz，原H0槽15 | `cmake --preset gcc` → `cmake --build build --parallel 2` | 通过 | 均通过 | 均通过 | 51.39 |
| libogg，原H1槽6 | `./autogen.sh` → `./configure` → `make -j2` | 通过 | 均通过 | 均通过 | 31.43 |

两条路径均无交接、0模型请求；miniz实际观察目录为`build`，libogg生成脚本后仍是unknown且阶段未完，执行configure后才是passed。作者完整测试为main-build-v1的not_required，不写成测试用例通过。libogg原H0槽18是同类分步缺口，没有另加一次重复来增加样本。

47项相关回归通过，覆盖阶段中间失败、最终配置文件缺失、旧Cache不能代替当前目录、输出目录越界、源码保护、状态路由、既有Harness注入等。修改文件Ruff和格式通过；全仓`make -C backend lint`的Ruff检查通过，但当前Ruff0.17.4对未修改的`tests/test_recovery_ablation.py:21`要求新增空行，格式检查失败。用HEAD原文件复现同一失败，本轮不顺手改历史测试。完整产品/冻结测试以PR的CI结果为准。

## 证据与边界

原件：`/home/yiwei/.codex/outputs/forge-workflow-configuration-repair-2026-11-09-v2/`。`run_checks.py`、`scope.json`和`source-snapshot/`保存驱动、输入来源与实际运行代码；`summary.json`及两项目的`result.json`、Session日志/重放记录保存实际结果；`verification-v2.json`保存阶段观察及4容器的8项名称/ID不存在检查。

准备v1在创建空脚本模型时漏传`responses`，尚未启动构建即停止，原日志保留于同名前缀`-v1`；独立v2补齐该参数后执行。首次只读核对`verification.json`把Docker小写`no such object`误当成未确认清理，保留原件，由`verification-v2.json`记录正确的只读核对；没有重跑构建。

本结果支持这两种合法方案可以由修复后的执行器完成，不估计模型成功率、Harness更新收益或一般兼容率；E51仍为H0 10/12、H1 11/12。下一步在该共同底座上，以近期轨迹设计更短的离线Harness候选与新比较，不把本次人工修复计入自动优化收益。
