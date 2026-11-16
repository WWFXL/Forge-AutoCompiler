# 本轮Harness更新18项目比较准备

## 已固定的研究设计

Issue #809，身份`cpp-build-harness-update-comparison-flash-v1`。用户要求包含libffi的18项目、两个版本各一次，共36槽，只汇总全18项目；结果先审核，不自动写论文。两组独立初始规划，不复用成功命令、不检索经验库。更新组恢复阶段使用已经审核的错误经验，规划阶段只增加通用依赖检查和真实容器查询。

本轮采用LH_v0_common与LH_v1：原P0/R2源码读取能力对比本轮依赖查询、诊断记忆、组合查询及恢复经验。共同使用修复后的执行器、Token容量、镜像、文件后审政策和主构建验收。这里比较领域Harness组合更新，不把历史49KB容量中断作为基线能力，也不能单独归因某条经验。

权威协议：[预注册](../../benchmarks/preregistrations/cpp-build-harness-update-comparison-flash-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-harness-update-comparison-flash-v1.json)，SHA-256 `e5156a46ce285c4e9fb1d525a43a65731047b06dc119ce86a422111f340f34c0`。项目版本、归档SHA、作者主产物引文、CLI检查及历史暴露见[任务](../../benchmarks/fixtures/harness-update-comparison-v1/tasks.json)。源码18/18取得，固定CMake 6、Make 5、Autotools 7；smenu源码核实为Autotools，来源预选标签保留。

## 必要验证

8项相关检查通过，覆盖18项目36槽、AB/BA顺序、两组任务一致及工具/经验隔离、无授权不调用、全18报告保留未观察，以及共享恢复装配。Ruff、格式与实际归档CLI检查通过；18项目参考声明逐条核对源码行和SHA。没有重做产品全测或给18项目先灌入成功命令。

两次零Provider真实libyaml构建，使用预写回复：配置成功→受控不存在target失败→恢复方案→主要库构建/交付→原归档干净重建→cleanup，均通过。基线没有注册环境工具；更新组初始与恢复各实际查询一次cmake。分别2/4次脚本回复、13.84/14.24秒，Token和新增模型费用均0；差值来自预写接线，不作模型效果。原输入均保持，新增构建文件后审。

另一次dsvpn独立参考构建及用法检查通过：作者无参数退出254，检查明确断言该码以及DSVPN/usage输出，避免把正常用法入口误记为构建失败。工程材料根：`/home/yiwei/.codex/outputs/forge-harness-update-engineering-2026-11-17-v1`，`summary.json`、`engineering.py`、`dsvpn-reference.log`和`inventory.json`，清单SHA `da3ef3265938df42a4f29b3a5f755ce320304d30fd15b6b3305c122385f38a18`。源码采集根：`/home/yiwei/.codex/outputs/forge-harness-update-sources-2026-11-17-v1`，18项目resolved与source-index-final保留。

## 当前状态

这是正式数据采集前的基础设施阶段，新增模型费用0、正式0/36，尚未读取凭据。拟本批硬上限10美元、确认起8小时，单槽0.60美元/1800秒，统一deepseek-flash；无自动重试/补槽，未知用量、模型身份异常或cleanup失败停止。用户已经批准范围和开始准备，尚未绑定本批新增费用及时窗；取得该项授权后直接运行，不重复审核方法和项目。

结果保留主构建、交付与重建层级，全部初始/失败/恢复请求及费用，按全18项目汇总并解释逐项目失败。libffi开发暴露及旧项目接触记录保留，不称最终holdout，不自动改论文/E57或回填旧失败。

## 后续执行（2026-11-17）

本节追加准备之后的事实，不改变以上准备时点状态。用户已授权本身份10美元/确认起8小时；PR810三CI通过并合bee79291后执行，Issue811跟踪的36/36采集结束，结果与失败分层见[结果报告](2026-11-17-harness-update-comparison-results.md)。结果待用户审核，未改论文。
