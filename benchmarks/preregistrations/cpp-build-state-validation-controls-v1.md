# 状态变化与分层验证正负控制 v1

跟踪#498，独立身份 `cpp-build-state-validation-controls-v1`。依据#470持续授权，0Provider/0模型费用。使用#484已经开发暴露的miniz/pigz/libite固定源码，不称新holdout。真实Docker执行须在#493串行参考批终结之后；不改运行中组件，不并行重型实验。

问题是已有合理规则和分层验证对哪些明确状态有辨识能力。这里不比较P1/P2效果，不调用修复Agent，不把受控变化伪装成自然失败，也不为复杂规则故意削弱基线。严格终点和原完整测试不降低。

固定七槽位、各一次、不替换：

| 顺序 | 项目/控制 | 固定变化 | 预期观察 |
| --- | --- | --- | --- |
| 1 | miniz正常 | 无 | 完整测试、精确交付、clean replay、cleanup后completed |
| 2 | miniz空测试 | 仅将初始配置的BUILD_TESTS=ON改为OFF；原源码/测试不改，原smoke命令及marker不变 | CTest即使exit0，也不能满足check完整输出；在check交接，不称测试失败或模型错误 |
| 3 | pigz正常 | 无 | 同上严格completed |
| 4 | pigz交付漂移 | 完整方案成功后，夹具向已暂存ELF末尾追加固定字节；单独记录注入事件及日志，不改源码和候选配方 | 原测试通过、结构/版本smoke仍可通过；replay重建正确原产物后size_mismatch拒绝。若提前失败，按实际记录，不能算预期控制通过 |
| 5 | libite正常 | 无 | 同上严格completed |
| 6 | libite遗漏bootstrap | 工作区完整执行autoreconf/configure/build/check/stage；仅候选recipe的显式command IDs漏掉bootstrap | 工作区测试通过；空源码replay的./configure不存在，recipe_execution_failed拒绝，保留原完整测试与全部命令历史 |
| 7 | miniz外部配置 | 完整方案后另一个执行方真实执行关闭测试的cmake配置，并追加权威configure记录 | 原Workflow发现command frontier变化、PlanContractError停止，不创建replay；这是命令新鲜度保护，不证明能发现无记录的任意文件变化 |

空测试及外部配置的关闭测试仅是故障注入，不是允许的成功配方；固定测试义务不变。交付漂移是验收夹具注入，不是合法Agent动作。遗漏bootstrap是候选配方缺陷，不是声称系统会自动生成这种方案。控制预期逐项冻结，基础设施异常、超时、清理失败或不同原因拒绝都不算预期成功。

各槽2CPU、方案32命令/最多1交接/900秒/单命令180秒，replay600秒；外部夹具命令120秒。无修订、不重试，失败保留继续；cleanup失败立即停止整批。UTC22:45前保留3000秒才能开始新槽；总截止UTC23:00及最后15分钟清理交接不变。固定镜像、源码归档SHA、方案与组件均写入manifest。只读审计父参考inventory后才开始。

保存完整Session/命令/日志/初始与最终Workflow状态、预定变化、原始源码普通文件哈希、逐层verification/replay结果及cleanup；seal后独立核验全部文件与源码快照。正常控制未通过不能宣称该组负控制已建立；七项均闭合也仅支持这四类已知缺口的开发资格，不支持自然误接受率、总体准确率、学习选择器增量或模型成本效果。

后续决策：已有规则足以区分的状态保留为解释与强基线；只有出现P1未覆盖且具有可执行非预知决策的状态，才设计P2。RQ1的新项目比较和RQ2真实接管分别使用新身份。不得续写本批或先看结果再改预期。
