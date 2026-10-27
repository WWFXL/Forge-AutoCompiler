# Flash完整策略比较与恢复贡献实验

Issue626。用户2026-10-27明确将实验模型从deepseek-v4-pro切换为deepseek-flash，并授权新增模型费用共享10美元、从确认起4小时、无自动重试。确认时点UTC08:44:30，截止UTC12:44:30（北京时间20:44:30），准备计入。允许新身份重新检查Provider；旧HTTP402/未知用量及停止记录保留，不续跑旧身份、不抵销旧预留。本轮首个实际实验请求同时检查服务可用性，无额外付费canary。

## 问题与固定比较

1. cpp-build-library-strategy-comparison-flash-v1：沿cpp-build-library-strategy-comparison-v2的rang/ELFIO×三策略×两重复12槽。全部共同任务、完整原测试、十默认示例、固定来源/依赖、精确交付、clean replay及调度保持，比较完整完成、请求、全费用及总耗时。
2. cpp-build-tool-recovery-ablation-flash-v1：沿cpp-build-tool-recovery-ablation-v1的snappy/simdutf/yaml-cpp/libtommath/tinyxml2×有恢复/无恢复10槽及原交替顺序。相同工具初始方案和共同执行器，唯一方法干预为失败后Agent接管。核对每对初始方案与首次失败前执行内容；不同则不作单开关归因。

所有项目已有开发暴露，非holdout。两组独立报告，不与旧Pro批次合并估计效果、显著性或模型排名。模型规划与工具规划Workflow共享装配/恢复，强工具Agent保留自身工具能力；不声称三者harness完全相同。结果有条件收益或代价均完整报告，不以全指标优势作为完成条件。

## 模型与费用

统一请求deepseek-flash、thinking enabled/low、最大输出32768、max_retries=0；接受公开当前版本DeepSeek-V4.1-Flash-1017或deepseek-flash的响应身份。官方2026-10-27价格https://api-docs.deepseek.com/quick_start/pricing：高峰缓存未命中输入0.30美元/M、输出1.20美元/M。本轮全部输入按该高峰未命中价保守估算，同时保留原始usage；不是账单或实际缓存费用。

原资源边界保持：每槽最多3美元、下次完整响应预留0.80美元、请求/Token/命令/步骤、600秒请求准入、3900秒新槽准入和完整replay时间保持。比较阶段最多8美元、恢复阶段最多5美元，按实际已结算支出及下一阶段预留共享用户10美元；不得把8+5误当13美元授权。未知用量、模型身份异常、实际cleanup失败停止所有新增付费；保留已观察失败和未观察后缀，无补槽、隐式重试或旧身份续跑。未使用预算不延长截止。

## 本轮交付

直接复用现有参考与执行器，仅核对本次改动相关检查，不重复参考构建或全量产品测试。完成后交付三策略结果表、五对恢复消融表、失败分类与轨迹、固定候选分层验证、可引用报告及原始证据链接。候选清单和运行授权分离；原未启动Pro候选保持不变。工程工作不能代替这些科研结果。
