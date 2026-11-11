# 成功准备与主构建交付的共同修复

本阶段为工程修复及已有轨迹分析，新增真实Provider调用和模型费用均为0，不产生Harness效果比较。E56的结果、失败与分母保持不变；论文未修改。跟踪Issue #744。

## 直接原因与改动

1. **Rnnoise的前置生成物被系统清掉。** 原槽35先成功执行prefetch-model与autogen，随后系统插入的configure角色清理步骤删除模型与configure，下一条`./configure`退出127。这先于后续discard_dependencies冲突，不能只归咎模型。现在依赖/配置变更需要清理时，系统清理动作作为dependency置于整个准备序列之前；记录dependency实际创建/更新的仓库生成物（仅文件身份元数据，不读大数据文件内容）；清理会删掉这类输出的步骤及其显式后继准备完成记录失效，重新执行后才可消费输出。没有仓库生成物且不依赖失效步骤的安装/外部准备继续复用。缺少输出记录时保守失效，不做Shell语义猜测；只改变build后缀、不触发清理时仍复用成功准备。实际有效步骤按相同顺序进入干净重建。
2. **修订反馈只揭示第一个冲突。** 成功依赖确需覆盖时仍要求明确理由，现在一次报告全部冲突ID，避免模型修正一个后又被第二个相同约束拒绝。系统清理步骤不伪装成模型可修改的成功依赖。
3. **同一组件有发布/中间变体。** toybox同时生成`toybox`和`generated/unstripped/toybox`。保留全部组件候选证据，同名同类型选距根目录最近、再按路径排序的一个交付。不会漏掉其他已要求组件；不同类型同名或不同组件的交付歧义仍拒绝。该确定性选择不是任意仓库的安装语义解析。
4. **运行副作用污染交付目录。** 明确使用`/artifacts`作为cwd的作者轻量命令改在仓库内独立的`.forge-verification/<step_id>`运行；实际二进制仍从`/artifacts`调用，使用宿主UID/GID执行。linenoise的0600历史文件由宿主用户持有，不混入交付清单。相同包装命令进入干净重建，退出码与输出断言保持；独立参考应使用交付二进制的绝对路径。
5. **参考定义不完整拖到构建后才暴露。** 新main_build运行在创建容器、请求构建模型之前检查独立参考的可执行组件轻量入口覆盖。缺少入口须由实验准备方依据作者源码补全；库组件不要求运行入口。不让恢复Agent猜测参数或修改裁判。snapraid的新独立参考绑定`--version`，源码`cmdline/snapraid.c:303,874–876`明确该选项及EXIT_SUCCESS。

## 实际验证

[工程汇总与容器实查](../../benchmarks/analyses/common-preparation-delivery-repair-2026-11-11/summary.json)：

| 项目 | 覆盖问题 | 主构建 | 干净重建 | 清理 |
|---|---|---|---|---|
| jansson | dependency执行真实autoreconf；受控错误目标后改变configure，先清理再生成configure | 通过 | 通过 | 通过 |
| toybox | 发布与unstripped同名版本，选择主交付 | 通过 | 通过 | 通过 |
| linenoise | 实际交互运行生成history.txt，隔离cwd及宿主权限 | 通过 | 通过 | 通过 |
| snapraid v2 | 作者明确版本命令；无参考入口须在运行前拒绝 | 通过 | 通过 | 通过 |

jansson使用一次脚本化零Token恢复回复，不能称真实模型恢复效果。四项目均原源码保护通过。总共实际执行6条工程路径（4个独立项目），时长及容器实查见汇总。初版v1的snapraid用通用默认旗标完成，但该回退未被采纳；随后恢复作者入口要求，独立v2以作者`--version`完成。两次均保留，不替换或回填。v1其余三项目本来就使用明确作者入口/纯库检查，不受该回退影响。v3仅重新验证jansson的最终生成物感知失效/安装复用实现，不重做其他三个项目，也不增加独立项目分母。

原件：`/home/yiwei/.codex/outputs/forge-common-preparation-delivery-repair-v1`与`/home/yiwei/.codex/outputs/forge-common-preparation-delivery-repair-v2`、`/home/yiwei/.codex/outputs/forge-common-preparation-delivery-repair-v3`。scope、cases、源码快照、每次result/session/recipe/replay及失败命令均在各自目录。它们是工程验证，不替代E56自然效果。Rnnoise本身未重跑；其清理顺序机制用jansson真实bootstrap与针对性Shell回归验证，不能宣称已观察Rnnoise端到端成功。

相关回归按现有fixture插件边界分组执行，最终124项通过；一次合并收集的13项fixture未注册错误为开发检查限制，不计科研失败或效果。Ruff及格式检查通过，未运行本地产品全测。

## 修复到此结束，转待审Harness设计

[Codex规划Harness诊断与待审P4](2026-11-11-codex-planning-harness-proposal.md)说明新的证据：已有“只展示提交工具”的收敛状态并未阻止已注册读取工具继续执行。这与初始规划成本有关，尚未在本轮修改；提案明确区分应共同修正的工具分派约束与待比较的规划策略，不保留接口缺陷来制造候选优势。先交用户审核再实现比较，结果再审后才能入论文。
