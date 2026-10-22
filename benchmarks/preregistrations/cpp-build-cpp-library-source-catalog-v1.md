# 固定C++库来源目录v1

Issue #621。原30项来源与任务分母保持。本身份只为扩大C++库来源进行元数据采集，不按本批策略效果选择项目。范围明确为GitHub指定检索框下的C++库，非C++总体代表样本。

固定query：`language:C++ archived:false fork:false topic:cpp-library stars:100..5000`；stars降序第一页20项，不翻页/替换/补位，先封存全部排名，再依次取得默认分支ref→Git commit对象→根tree。只用Git对象API，不使用附带patch的commits API、不读源码blob/README、不构建。header-only与多入口均原样保留，元数据不能授予构建资格。

记录当前跟踪benchmarks/docs/research有限精确owner/name暴露，允许URL的.git后缀，拒绝仓库名或owner前后缀误匹配；不是全部历史、训练未见或holdout证明。全部task_qualified=false、测试/源码图/交付/构建资格未观察。

0模型Provider/模型凭据/Token/费用/Docker/构建。每请求25秒无自动重试，失败保留并继续固定后项。沿原4小时窗口UTC2026-10-22 15:37:37–19:37:37，准备计入，截止前60秒不新请求，不延期。共享自设20美元剩余额度不因本零费用阶段重置。

复用现有GitHub元数据/typed evidence，仅做固定分母与无patch边界两项局部检查。采集后独立重建Git根tree对象，核验ref/commit/tree、排名、检索范围、暴露登记、冻结源码与完整typed inventory。失败与未观察保留，不从来源数推出方法成功率。最终HEAD三CI后仅合科研依赖分支，知识库同步，RQ3/P2/主线/用户HTML保持。
