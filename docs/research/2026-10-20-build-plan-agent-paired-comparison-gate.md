# 六仓库双执行路径的真实Docker接线门禁

Issue #502，独立协议`cpp-build-plan-agent-paired-comparison-v1`，协议/门禁运行release `54d1d893d95d3167f704d547a8799011330d8738`；manifest SHA-256 `5f2cc841c38b1ed8eaee5867d2491dfce060c539aa9c3c92170729bbc74f42f2`，59组件绑定。依照预注册只执行第一重复12臂，不重复同输入第二次接线；0Provider、0Token、0模型费用。

uncrustify、libhydrogen、libsodium、libsndfile、buffer、libverto的plan/tool两执行路径全部严格completed，12/12，无重试、替换或缺槽。完整固定测试、原始源码普通文件不变、精确交付、空源码clean replay及交付集合/类型/大小/SHA-256/smoke一致、cleanup全部通过。原始命令与测试日志全部保留；两条路径共同使用command300s/replay600s，未降低原固定验收。

原始证据`/home/yiwei/.codex/outputs/forge-plan-agent-paired-gate-v1/`，72,368普通文件/92链接/578,913,379 bytes；inventory canonical SHA-256 `9f304ea1a1a134e6d2dc491b9815e9a328f6c05e40173f018e44c99b4c13abc3`。独立stdlib审计`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/paired-gate-v1-audit.json` valid=true：全量typed inventory、59组件快照、原始归档及源码基线、12槽顺序、请求生命周期/零用量、固定测试实际日志、严格Session/replay和对应容器清理均通过。审计不导入被测runner；已先用旧v2八臂证据复核审计工具。0对应受管容器残留。

本门禁使用人工reference recipe和脚本化模型，只证明相同固定任务能由两种执行路径完成，不证明模型构建能力、方法效果、状态适应增量或总体成功率。脚本化模型请求数不作效率比较；参考recipe及个人知识库不得进入真实模型上下文。

准入决定：可以按用户#470跨阶段授权开始同manifest的24真实槽、12配对采集，阶段最多$12、共享新增$20。新臂和新请求保留3600秒；用量未知或cleanup失败停阶段，缺槽明确未观察；普通可计量方法失败保留并继续。只有24槽完整且usage闭合才作冻结固定任务集整体配对描述，不作OSS总体、非劣或成熟Agent排名；没有修订激活不能证明RQ2。
