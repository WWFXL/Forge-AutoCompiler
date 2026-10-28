# 统一条件三系统比较：设计与执行准备

核对日期：2026-10-29。跟踪：[Issue #640](https://github.com/WWFXL/Forge-AutoCompiler/issues/640)。本阶段为论文系统比较消除执行阻塞，属于基础设施准备，不是新的模型效果实验。

## 已落实的比较

问题：完整构建任务、资源及验收相同时，Forge模型规划＋Workflow＋配置状态动作选择，相对强工具Agent和CXXCrafter社区版，在完整完成、全部费用、耗时和恢复行为上有什么取舍？优势、持平或劣势都保留，不要求全面胜出。

固定8项目×3系统×2重复=48槽，每系统16槽：原六任务check/simdutf/snappy/yaml-cpp/libtommath/tinyxml2，加已具备完整任务的rang/ELFIO。全部已经开发暴露，不根据新结果换样、不称holdout，不把重复当独立项目。精确commit/归档/任务/顺序/暴露登记在[manifest](../../benchmarks/manifests/cpp-build-unified-system-comparison-flash-v1.json)，详细边界见[预注册](../../benchmarks/preregistrations/cpp-build-unified-system-comparison-flash-v1.md)。

|系统|执行方式|保留的差异|
|---|---|---|
|Forge|新模型规划→GoalStateWorkflow→有依据的BOOL修订或失败Agent→完整验证|显式配置状态作用于现有CMake目标，Make/Autotools沿普通Workflow|
|强工具Agent|共同任务→原工具Agent逐步操作→固定测试和自动配方提交|与Forge共用候选/反馈修复和计量，不注入Workflow状态动作|
|CXXCrafter社区版|原生Parser/Generator/Modifier/两级Judge→共同外部验收→无缓存Dockerfile重建|既有固定社区快照及运行修复，非论文原版；外部失败不反馈Modifier|

CXX内部最多10版Dockerfile，Forge沿原两次handoff/8轮规划及工具限制；不声称Harness或决策预算完全相同。本次是完整系统比较，前一固定方案实验用于分离状态检查/直接动作；独立初始规划差异不能当纯状态因果。

## 对旧参考修正的具体问题

1. 三方每次模型请求均得到同一完整公开任务JSON，包括固定检查脚本、测试准备和显式配置目标，Forge不再只有长脚本引用。额外上下文Token计费。
2. CMake统一build目录及Release，新增单独公开配置检查，原作者测试命令字节保持；Make/Autotools保持作者默认优化并在分析中核对，不把更轻构建当状态收益。原归档、依赖资源、固定image ID、root和可安装真实依赖的网络权限相同，不提供正确参考命令。
3. 三方2个并行作业。CXX只固定Dockerfile的FROM与CMake/CTest/Make环境，native/effective字节保存；CXX构建沿两个可用CPU的affinity限制，Forge沿2CPU quota，具体方式披露。外部测试也显式设置并行环境，修正旧遗漏。
4. 每槽45分钟上限、最后5分钟清理；新槽须剩45分钟，模型请求只须剩10分钟，完整重放须剩25分钟。Forge和CXX重建准入同步，避免旧内外层时限不一致。45分钟不是每次模型请求的预留。
5. 初始读取/规划、失败、纠错、恢复及CXX内部审查/Judge全部计费。槽外异常也保留已记录用量。未知用量、身份或清理异常停止整批，无自动重试/补槽，时间截断和未观察单列。

## 必要执行验证

13项本次/相邻针对性检查、Ruff及候选CLI通过，未重跑八项目人工参考或本地全量产品测试。

独立开发身份`cpp-build-unified-system-dispatch-check-v1`使用tinyxml2既有自然方案与CXX六响应脚本回放，经真实新入口完成：

|入口|构建/原测试/精确交付/完整重放/清理|槽耗时|脚本响应|
|---|---|---|---|
|Forge|通过|11.41秒|1|
|强工具Agent|通过|11.46秒|1|
|CXX社区原生循环|通过|41.16秒|6|

0真实Provider、0Token、0模型费、未读取真实凭据。CXX的Parser/文档分析/Generator/审查/两Judge均经过脚本响应，Dockerfile实际构建和无缓存重建、外部原测试及交付均执行。这只证明新适配可以端到端运行，不估真实模型效果、费用或排名。原子结果继承旧runner的`real_model_development_canary`类别字样，必须以开发protocol的零Provider身份和响应来源解释。

raw：`/home/yiwei/.codex/outputs/forge-unified-system-preparation-2026-10-29/dispatch-check-v1`；inventory `2a1346e5975b3d516b790c73bf30be04758bf95098c0a3d61dac55038502ae72`；[版本化开发分析](../../benchmarks/analyses/cpp-build-unified-system-dispatch-check-v1.json)。当前开发容器一次实际核对全部不存在，未重复旧批次审计。上层会话保留运行脚本、原日志和收据。

开发候选草稿SHA `c1954635d2e75746234f9069ac73b138db89efe9b5529fdc2413fe9cfaefc34e`保留在会话`candidate-development-draft.json`。随后仅把候选构造的归档索引读取改为复用同一父manifest索引，使CI不依赖本机归档；运行前仍核对归档SHA。开发代码快照不改，正式授权绑定发布manifest字节。

## 启动与论文交付

入口`scripts/forge_build_system_comparison.py`。backend环境中`uv run python ../scripts/forge_build_system_comparison.py --check-prepared`不读凭据；正式执行沿既有`--candidate`、`--authorization-root`、`--output-root`参数与账本，输出根必须不存在。`--analyze`生成逐方法摘要，进一步分析须区分未完成/时间截断，并提取初始/恢复费用及分层验证。

当前只有免费准备授权，48槽未启动。候选设计新增上限10美元，建议新8小时窗口，准备计入；窗口不保证48槽必定完成，剩余槽记未观察。用户确认后绑定发布候选SHA直接采集，不重复资格链。

真实运行后产出固定48槽系统主表、项目/构建系统分层、全部初始与恢复费用、状态动作案例和测试/交付/replay层级结果，登记[论文证据索引](THESIS_EVIDENCE_INDEX.md)。原源码/原测试边界和前期失败保持。
