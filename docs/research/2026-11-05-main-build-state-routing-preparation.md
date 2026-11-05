# 主构建目标与异常状态语义路由：实现及比较准备

2026-11-05，Issue #693。本阶段是工程修复与实验准备，未产生Jev效果数据。

新main-build-v1只以主程序/主库构建与有效产物为主要目标，作者完整测试明确not_required；旧完整任务指标留空，不重新解释历史失败。源码保持、精确交付与干净构建重放单独记录。实际成功build记录加独立主要产物检查取代命令文本必须被识别为build的硬门槛，Workflow与工具Agent共同采用。

新增BuildStateRouter将阶段目标、实际退出/日志、配置和主要产物观察组成状态包。规则/Jev共享作者最低CMake版本安装、已有配置恢复、不完整产物重观察等有依据的候选。正常路径不调用Jev；无候选交恢复Agent。Jev用两个Choice输出状态类别与候选动作，不能生成Shell、修改源码/测试或覆盖独立结果。每槽最多两个不同局部动作，局部失败保留并可转Agent，不盲目重试。新身份不恢复旧Jev控制器或安全阈值，不预设新组件有收益。

45项相关检查通过，包含真实本机构建变量调用、仅声明build无产物的反例、工具Agent共同提交、新范围不执行完整作者测试、SDK零网络请求合同/费用及异常停止。Ruff与变更格式检查通过。没有运行产品全测替代实验。

真实Docker工程路径：jsoncpp以变量形式调用cmake并完成主构建、交付、干净重放；double-conversion保留原CMake版本不足失败，再由一次规则候选安装作者要求版本并重建，主构建/交付/干净重放通过。两路径源码与cleanup通过，真实模型请求/Token/新增模型费均0；pip工具安装属于真实构建网络动作。工程原件`/home/yiwei/.codex/outputs/forge-main-state-engineering-2026-11-05-v1`，结果及engineering-summary.json保存实际记录，不计正式效果分母。

准备独立cpp-build-main-state-routing-comparison-v1：六项目固定E48首重复基础Forge初始方案×两重复×规则/Jev=24。Flash恢复、资源、初始方案、候选、经验关闭与主构建检查一致。源规划费用另列；已开发暴露、异常触发可能有限，必须报告真实触发分母，不称holdout或全系统规划效果。完整协议位于benchmarks/preregistrations/cpp-build-main-state-routing-comparison-v1.md。

用户当前“开始执行！”覆盖此前四步24次计划；助手自行收紧新增2美元及UTC05:38:28–09:38:28，准备计入、不续旧余额，无自动重试。准备提交后才绑定manifest和当前授权读取现有凭据；未知用量、模型身份或cleanup异常停止整批付费，保留原失败和未观察。
