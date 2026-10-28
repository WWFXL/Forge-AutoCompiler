# 统一条件下的 Forge／强工具 Agent／CXXCrafter 系统比较

状态：#640 免费实现准备；尚无本身份 Provider 授权或效果数据。新模型调用须绑定本候选 SHA、新预算和截止时间。旧30槽授权和余额不续用。

## 问题与方法

完整构建目标、资源及验收相同时，模型规划＋状态感知Workflow相对强工具Agent及可运行CXXCrafter社区版，在完成率、完整模型费用、耗时及恢复行为上有什么价值和取舍？优势、持平或劣势都保留。该实验比较完整系统；配置组件的因果解释沿用前一固定方案三臂实验，不用本实验的独立初始规划证明纯状态效应。

- Forge：共同完整任务→新模型规划→GoalStateWorkflow→有源码声明和真实BOOL缓存依据时直接修订，否则失败Agent→固定原测试、精确交付、同镜像完整重放。
- 强工具Agent：相同完整任务和Forge共同候选/反馈Harness；逐步使用原工具、原固定测试与自动配方提交，不注入Workflow的配置状态动作。
- CXXCrafter：前一轮固定社区快照，来源main `bac70e99e48b210a350c18b3f93efd839787ce37`，含先前已有运行修复。保留原生Parser、文档/依赖分析、Generator、Modifier、两级Judge及最多10版Dockerfile；不是论文原实现复现。仍将完整外部验收单独执行，外部失败不再反馈Modifier；这项反馈差异必须在结果表说明，不称同Harness或纯算法比较。

## 样本与任务

前瞻固定既有六任务清单，加已具备完整任务和参考结果的两个header-only项目；不根据新方法结果替换样本。全部已经开发暴露，重复非独立项目，不称holdout、不估总体成功率或显著性。

|任务／项目族|系统|原测试与交付|
|---|---|---|
|check|Autotools|原make check；libcheck.a|
|simdutf|CMake|原94注册测试、完整测试模式和工具；libsimdutf.a|
|snappy|CMake|原测试、benchmark保持开启；libsnappy.a|
|yaml-cpp|CMake|原3CTest；libyaml-cpp.a|
|libtommath|Make|原test完整入口；libtommath.a|
|tinyxml2|Make|原作者测试；libtinyxml2.a|
|rang|CMake|原6case/15subcase及三个原程序；精确交付三个程序|
|ELFIO|CMake|原73测试/74CTest及10默认示例；精确交付ELFIOTest|

精确commit、源码归档和SHA、全部验证命令、原作者声明摘录及项目族暴露登记在同名manifest。任务为8×3×2=48槽，各方法16槽；六种方法顺序轮换，第二重复错开三种顺序，顺序在观察前固定。不补槽、不重跑旧身份。独立初始规划全部重新计费，不复用历史方案或把人工参考输入正式Agent。

## 共同条件和必要适配

三方所有模型请求均得到同一完整公开任务JSON（含完整固定检查命令），不再一方读全文、一方仅得到长脚本SHA引用。Forge两方使用同一CommonTaskMeter；CXX原生各请求追加共同任务，新增上下文Token照实计费。工具权限、消息组织和内部反馈不同仍披露。

固定原`autocompiler:gcc13`不可变image ID、原root用户、`compile_network_wwf_v1`网络、允许安装真实依赖、2个CPU作业。原归档中已有`.forge-deps`资源相同；它们不是已安装包或正确命令。CXX原生Dockerfile只统一FROM和三个并行环境变量，保留模型自己的构建指令；native/effective字节均保存。Docker构建限定两个可用CPU；外部原测试和重放显式设置CMAKE_BUILD_PARALLEL_LEVEL/CTEST_PARALLEL_LEVEL/MAKEFLAGS，修复旧参考测试并行遗漏。

CMake统一`build/`目录与Release，并新增单独公开配置检查；完整原测试命令字节保持。Make/Autotools保持作者默认优化参数，禁止自行覆盖，并在结果分析中检查实际构建参数；若偏离须单独标注，不能把更轻构建当状态收益。CMake组件只处理现有显式BOOL目标；Make/Autotools使用普通Workflow＋失败Agent。禁止伪造HAVE_*依赖探测结果。

原源码、原测试、依赖输入及符号链接保持；允许新增正常生成文件，不允许改写原有输入。原完整测试、精确产物集合/结构/大小/SHA、完整同镜像clean replay和cleanup保持。CXX外部评价分别记录原/重建测试、源码、交付、cleanup和产物字节一致性；其内部Judge成功不替代完整完成。

## 预算、时间与停止

候选设计新增费用上限10美元，建议新8小时，准备计入。只有用户确认后才保存有效授权，读取凭据并运行。统一deepseek-flash、thinking low、输出32768、HTTP240秒、SDK自动重试0；采用既有Flash接受身份，输入0.30/输出1.20美元每百万Token按未命中估费，非实际账单。

每槽上限2700秒（45分钟），最后300秒留清理；新槽须剩2700秒，单请求须剩600秒，重放须完整1200＋300秒。Forge内部重放与外层一致；CXX也在无缓存重建前检查1200＋300，避免旧外层/内部不一致。45分钟是安全上限而非每次请求必须预留；预期多数槽远短于上限。两种Forge方法保留原1200秒Workflow、两次handoff、8轮探索及既有请求/工具限制；CXX保留原生10版上限。不同内循环限制写入对照，不声称完全相同决策预算。

每槽最多3美元，整批启动下一槽须剩3美元保守余量；CXX全部Parser、文档读取、审查、Judge、Modifier及失败费用计入，Forge初始读取/规划/纠错/恢复全部计入。未知用量、响应身份异常、清理失败停止整批；无自动重试、无成功替补。时间或费用准入停止后的余槽标未观察；已尝试但截断另记，不能填成能力失败。操作员停止同样保留轨迹和费用。

## 结果交付

主要表固定48槽，逐方法16槽报告完整/未完整/未观察、全部费用和累计时间；再按项目和构建系统分层。失败短时低费不算效率收益；共同完成配对仅辅助，标明按结果条件化。分开初始/恢复费用、真实配置观察/直接动作/Agent恢复、完整作者测试与交付/replay层，原分母和失败保留。CXX无对应阶段时保留原生类别，不强配同名阶段。

新结果报告、版本化analysis、原始输出路径/库存、运行revision及论文用途加入`THESIS_EVIDENCE_INDEX.md`/目录。完整原始输入/响应和失败不因后续实验覆盖。本准备仅消除真实比较阻塞，不记为新增科研效果；不重复八项目人工参考构建或全量产品测试，不扩规则大全、分类器或递归Harness。
