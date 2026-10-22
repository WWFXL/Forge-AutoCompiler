# 分层时间准入、共同测试准备与三策略真实比较结果

Issue #617；日期2026-10-22。主线保持“面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究”。本报告分别标明必要接口修复、rtorrent真实开发探针、环境诊断和独立三策略比较；工程检查不代替方法效果。

## 执行范围

- 第1步：模型请求准入由统一3900秒改600秒；新槽仍需3900秒，命令按剩余时间减300秒清理，clean replay须完整1200+300秒。HTTP240秒是传输超时，另有整批截止watchdog，不声称绝对响应时长。
- 第2步：三策略被调用的Agent获得相同原源码测试声明/固定测试准备义务，明确测试程序构建与运行是两阶段；确定性工具模板仍既有task-selected生成逻辑，不宣称它已解析新增文字义务，不按项目手写正确指令。不注入人工参考配方或个人知识库。
- 第3步：rtorrent单模型Workflow独立真实探针已封存；9请求/222963Token/$0.40385532/未知0，末响应32768输出截断，未交方案；仅源码准备，后续编译/作者测试/正式交付/replay未观察，strict0/1。未证明共同测试准备解决困难任务。
- 第4步：独立v3固定六项目×三策略×一次，六排列顺序，费用包含初始/读取/失败/纠错/恢复。v1/v2环境诊断独立封存，不并入比较分母。

## v3策略比较

| 策略 | 严格完成/启动槽 | 请求数 | 总Token | 估费（美元） | 总槽耗时（分钟） |
|---|---:|---:|---:|---:|---:|
| 工具规划＋Workflow＋失败Agent | 5/6 | 11 | 222520 | 0.37093584 | 21.37 |
| 模型规划＋Workflow＋失败Agent | 5/6 | 31 | 541381 | 0.86618796 | 28.02 |
| 强工具Agent | 5/6 | 58 | 695329 | 0.97531764 | 20.98 |

总槽耗时是各槽从准备到清理的顺序实测时间之和，不是纯模型推理时间。价格按输入$1.32/M、输出$3.96/M保守复算，非Provider账单。

| 项目 | 工具规划 | 模型规划 | 强工具Agent |
|---|---|---|---|
| yaml-cpp | 严格完成；4请求；$0.14254680 | 严格完成；4请求；$0.08126052 | 严格完成；11请求；$0.21551376 |
| snappy | 严格完成；4请求；$0.13385328 | 严格完成；11请求；$0.35085468 | 严格完成；23请求；$0.42257424 |
| simdutf | 严格完成；0请求；$0 | 严格完成；10请求；$0.30294660 | 严格完成；7请求；$0.09627948 |
| tinyxml2 | 严格完成；0请求；$0 | 严格完成；2请求；$0.04944984 | 严格完成；7请求；$0.08069424 |
| check | 未完成（有观察）；0请求；$0 | 未完成（有观察）；0请求；$0 | 未完成（有观察）；0请求；$0 |
| libtommath | 严格完成；3请求；$0.09453576 | 严格完成；4请求；$0.08167632 | 严格完成；10请求；$0.16025592 |

v3原18分母保留；check三槽为共同准备失败、首次策略操作未发生、Provider为0。其余五项目15/15严格完成，实际方法比较只覆盖CMake/Make；不能把三个check前置失败解释成策略不会Autotools。

## 独立check源码索引开发验证

原check归档有262普通文件+两个原悬空链接，旧is_file哈希集合漏链接，Git正确索引264条目。新适配器只纠正共同源码索引，原check PlanTask、固定make check、源SHA、模型、资源、精确交付与replay逐字不改；额外核对原执行与重放的原链接目标。两局部回归1.75秒、实际原归档Git准备通过，0Provider/0完整免费构建。旧准备实现/原失败/raw不改。

| 策略 | 严格完成/启动 | 请求 | 估费（美元） | 分钟 |
|---|---:|---:|---:|---:|
| 工具规划＋Workflow＋失败Agent | 1/1 | 2 | 0.09242244 | 10.01 |
| 模型规划＋Workflow＋失败Agent | 1/1 | 3 | 0.13766148 | 10.68 |
| 强工具Agent | 1/1 | 10 | 0.17934840 | 10.45 |

此probe为单个已见Autotools项目的独立开发验证，不补v3三槽、不与v3合并成功率或效应，也不把工程修复前后差异当方法收益。新raw为forge-check-source-index-probe-v1，release 526c69c58812824c0fd12fe1342d323bea8b0911，inventory 945b308a1050e9ef5e45cb87bcb0a6c03d88cb71bebc9538417aad57f752bae1；候选5220078dbba2e9c85eaf2f5172ce990c59f6783873140d6f548860360d0a6c6f/320组件。全部源/任务不变、链接目标和实际Git索引另经独立核验。

## 初始规划与恢复成本

| 策略 | 阶段 | 请求数 | 估费（美元） |
|---|---|---:|---:|
| 工具规划＋Workflow＋失败Agent | recovery | 11 | 0.37093584 |
| 模型规划＋Workflow＋失败Agent | initial | 17 | 0.35427876 |
| 模型规划＋Workflow＋失败Agent | recovery | 14 | 0.51190920 |
| 强工具Agent | agent_control | 58 | 0.97531764 |

v3模型初始规划五项目平均$0.070855752；check前置失败未进入规划，不以六项目计算该平均。工具规划的确定性生成本身为0模型费；其初始拒答升级和失败恢复分别记initial_abstention/recovery。模型规划初始读取、结构纠错和提交均计initial。强工具策略整体记agent_control，不人为切出一个等价“规划调用”。两Workflow共用测试、装配与恢复；强工具是保留完整能力的策略参照，工具集合不完全相同，不能作纯规划组件单因素因果解释。

## 恢复和失败解释

- yaml-cpp / tool_plan_workflow：strict=True，handoff=1，applied_revision=1，session=completed，replay=['passed']；error=None。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- snappy / model_plan_workflow：strict=True，handoff=1，applied_revision=1，session=completed，replay=['passed']；error=None。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- snappy / tool_plan_workflow：strict=True，handoff=1，applied_revision=1，session=completed，replay=['passed']；error=None。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- simdutf / model_plan_workflow：strict=True，handoff=1，applied_revision=1，session=completed，replay=['passed']；error=None。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- check / strong_tool_agent：strict=False，handoff=0，applied_revision=0，session=failed，replay=[]；error=共同源码准备失败：停止于首次模型/模板操作之前。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- check / tool_plan_workflow：strict=False，handoff=0，applied_revision=0，session=failed，replay=[]；error=共同源码准备失败：停止于首次模型/模板操作之前。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- check / model_plan_workflow：strict=False，handoff=0，applied_revision=0，session=failed，replay=[]；error=共同源码准备失败：停止于首次模型/模板操作之前。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。
- libtommath / tool_plan_workflow：strict=True，handoff=2，applied_revision=2，session=completed，replay=['passed']；error=None。原始smoke尾部及未改源码清单见派生JSON和raw，不把未启动功能测试称为测试用例失败。

## 两项环境事故与费用保留

v1误将generic项目套入rtorrent的非root/禁网配置；snappy原资格依赖root/原网络安装开发包。保留4完整槽、1中断槽、13未启动；原root写4rows/14未观察/lifecycle=false和unknown0的漏计不改。独立逐响应补核v1全已知$1.65622248，未知1次按$0.80预留；原第5槽已有8请求/7响应，停止未及时阻止下一槽，不能说及时停在边界。5实际容器cleanup成功，operator_reconciled为财务闭合，不是实验lifecycle成功。

v2恢复root/网络但仍注入FORGE_HOST_UID/GID，非root宿主finalize对容器root文件chown失败。yaml两个Workflow完整测试/精确交付/clean replay通过，strict=false保留。SIGINT被原槽级分类器吞掉后进入下一槽，随后在已知Provider响应后SIGTERM停止。保留3progress/4启动/14未启动；15请求15响应/$0.29805996/未知0，标准result不存在，operator-terminal.json记录中断，剩余一容器按managed/session/thread身份移除。不得拼这两个环境诊断入v3排名。

v3恢复原generic不配置host ownership identity的宿主模式，容器仍root/原网络；不改产品归一化实现、作者源/测试/精确交付/replay裁判。新整批停止标记防止operator stop作为槽失败继续发请求，ownership错误也停批。实际root文件写入→原manager→finalize/容器移除微检查及7局部检查1.17秒/Ruff通过；没有重复完整免费构建资格或本地全量产品测试。所见pytest旧临时目录权限清理警告与新7项通过分开，未修改历史目录。

## 共享边界与核验

- 全本轮已知估费：$4.98001152；未知1次预留$0.80；保守占用$5.78001152，低于原自设$20。新v3预留$16.50未重置前费；全部阶段财务闭合，旧unknown永不回填或重发。
- 原窗口UTC07:03:54–11:03:54，准备计入；当前授权为用户执行1234与既有直接实验/费用/发布授权，20美元/4小时为执行器自设本批边界。无自动重试、不补槽、不延长。
- v3未启动0槽；原stop_reason=None。未观察不填通过/失败。
- 独立stdlib重新计算新raw完整typed inventory、按运行release Git读取全部冻结组件并与source-snapshot核对、全部请求/响应原usage与费用、共同材料、源码及实际容器不存在；审计脚本不导入原实验评分实现。只审计本轮新raw，不反复扫描旧资格树。

## 结论边界与下一步

在本批已见项目的单次观察中，工具规划Workflow与强工具Agent严格完成数相同，估费低61.97%，总槽耗时高1.84%；模型规划Workflow估费低11.19%，总槽耗时高33.53%。这些是当前样本的描述统计，支持继续验证低成本工具方案与失败升级路线，不要求所有指标同时胜出。模型先规划的初始部分17请求/$0.35427876，五个实际进入规划的项目平均$0.070855752；其恢复另14请求/$0.51190920。不能仅比较请求数推断费用，也不能据本批断言模型规划在所有项目都无用。

simdutf与tinyxml2的工具Workflow均0模型请求严格完成，直接支持“部分仓库无需模型参与即可完整构建和验证”的观察。工具在其余三项目发生4次handoff并应用4次修订；强工具的内部命令纠错不以Workflow handoff计数，因此不能把其0 handoff解释成0恢复。

具体恢复轨迹：yaml-cpp工具方案完成默认构建但没有开启YAML_CPP_BUILD_TESTS，Agent修订配置后重跑后缀并通过3项CTest及重放；snappy模型初始方案关闭必需benchmark，工具默认方案缺少lzo2相关能力，分别从真实记录修订依赖/清缓存/配置后完成；simdutf模型方案已编译到100%，却误报build/libsimdutf.a而触发路径检查exit86，改成build/src/libsimdutf.a后通过94项CTest及重放。这些分别属于测试准备、依赖/目标和产物定位问题，不能统称为编译器失败。

独立check探针三策略均完成。工具模板首次拒答后调用1次Agent取得初始动作，再用1次恢复；模型规划为2次初始加1次恢复；强工具在完整Agent流程内纠正构建错误。共同源码索引修复消除了前置阻塞，但该开发探针不估计修复的因果增益，也不补主比较分母。

rtorrent仍是困难负结果：本轮未交方案，不能因一般项目已有收益就认定复杂多依赖任务已解决。后续保留模型规划和强工具基线，优先对已冻结来源/暴露登记做更广项目及重复比较，观察何时工具可直接完成、何时需要升级、升级后是否值得；将rtorrent准备不收敛作为独立有界诊断，不继续仅靠增加预算。下一研究问题是策略适用范围与恢复贡献，不是再增加大批基础设施检查。

样本为4个C++和2个C仓库，CMake/Make/Autotools三系统，全已见、每策略每项目仅一次；v1/v2新增轨迹已前瞻登记。不能称六个独立C++项目族、holdout、总体模型排名、统计显著性或跨工程版本单因素因果。共同测试准备没有单独消融；本轮未单独估计分层时间准入的独立收益。允许局部收益和成本取舍，不以全局严格优势否定硕士路线。RQ3旧分母、P2和论文主线保持。

## 证据入口

- v3运行release：`f1779887ab1f0fbfb49b0b6cf6ca02d8fecba03f`；candidate：`5eac1615473f3ed1248d36477eeff04ded40bf49a312c692fc77adb796f0e97f` /315组件。
- v3 raw：`/home/yiwei/.codex/outputs/forge-test-preparation-comparison-v3`；inventory SHA256 `8df8b315c670b306f833b0c4d8e8811cd1e3d7f4ee0e11745318d6952f24c661`。
- 预注册：`benchmarks/preregistrations/cpp-build-test-preparation-comparison-v3.md`；冻结候选同名manifests JSON。
- 独立audit、原共享账本、两事故reconciliation、停止意图及收据：`/home/yiwei/.codex/outputs/forge-test-preparation-session-2026-10-22`。
- rtorrent raw及v1/v2 diagnostic raw同会话记录，各独立inventory，不续跑旧身份。
- 版本化派生：`benchmarks/analyses/cpp-build-test-preparation-comparison-v3-results.json`。
- 代码/结果发布以PR618最终HEAD三项CI及实际merge/Issue关闭回读为准，仅科研依赖分支，不进main。
