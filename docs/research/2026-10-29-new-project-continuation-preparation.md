# 新项目三系统比较：未启动24槽的续段准备

跟踪[Issue #650](https://github.com/WWFXL/Forge-AutoCompiler/issues/650)。本阶段是实验准备，未读取真实模型凭据、未创建正式attempt、0新增Provider请求／模型费；不是模型效果实验。

## 续段回答什么

原七项目比较只保留17原终态、1中断及24未观察，见[原部分结果](2026-10-29-new-project-system-comparison-results.md)。继续推进原研究问题：在这些固定新项目任务上，Forge模型规划＋状态Workflow＋失败Agent相对强工具Agent与CXXCrafter社区版有什么完成、费用与耗时取舍？本阶段为收集余下数据准备独立身份，不重复参考构建或修改方法。

新身份`cpp-build-new-project-system-continuation-flash-v1`精确取原`schedule[18:]`：FSE第一次三方运行＋七项目第二次三方运行，共24槽、每方8槽。新槽1–24逐一映射原19–42，顺序不变；原1–18排除，旧失败及CXX/libsrtp中断槽不重试。原42分母、原始缺失文件及封存库存保持不变。

## 已完成的准备

入口[scripts/forge_build_new_project_continuation.py](../../scripts/forge_build_new_project_continuation.py)直接复用原三系统执行、Flash计量及父分析的动态分母。新增的内容仅为独立身份、精确后缀、原槽映射与父证据指针；全部347个父组件SHA及任务／模型／资源／验收条件保持。新候选共350组件。

候选：[manifest](../../benchmarks/manifests/cpp-build-new-project-system-continuation-flash-v1.json)，SHA256 `182cd9bad1a59d96c8a43dde590e402c6ea296cd858676203bddedb4cb94f661`；[预注册](../../benchmarks/preregistrations/cpp-build-new-project-system-continuation-flash-v1.md)。候选绑定父manifest与显式中断登记SHA，父库存为`1ae33f4c1a05edf5af8db01c58ee8498f10183382e82faa48e971a6e4a42d79c`。

本次必要检查：续段与相邻新项目测试合计8项通过，验证精确未启动后缀、排除旧中断、方法条件不变、入口分派至原执行器、动态每方8槽及失败计费／缺失耗时登记；Ruff、CLI `--prepare`／`--check-prepared`通过。CLI核验了冻结组件、源码归档／索引和原基线文件；未执行新构建、旧资格链或本地产品全测。工程检查不计作新方法成功。

## 运行与分析边界

三方法、deepseek-flash thinking low、所有初始／失败／恢复费用、原源码／测试不变、精确交付、完整同镜像clean replay及cleanup均沿父协议。允许正常新增生成文件。CXX保留社区原生工具、外部反馈与CPU affinity差异，仍只作实现参考；本批不修补已见强工具失败，不称同Harness或纯状态组件因果。

建议新预算最多10美元、从确认起8小时，准备计入；无自动重试，未知用量／身份异常／清理失败即停。当前只是建议，尚未绑定本身份有效授权；旧账本已闭合，不续余额或时窗。新raw拟为`/home/yiwei/.codex/outputs/forge-new-project-system-continuation-flash-v1`，启动时必须不存在，沿原每槽／请求／重放准入，窗口不保证24次全完成。

正式结果以本24槽独立报告。旧17终态和1中断不混进本批；跨身份只能描述性合列覆盖情况，不回填原42槽，不称单一完整冻结实验。旧结果已见、重复非独立项目、时间／环境变化均披露。E30仍为最新完整系统结果，E32保持部分观察，配置组件解释沿E01独立消融。真实采集并分析后再登记效果条目。
