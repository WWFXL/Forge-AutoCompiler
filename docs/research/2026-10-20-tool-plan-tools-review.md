# 工具生成初始构建方案：来源核验与资格设计

Issue #540。用户要求参考CXXCrafter和CompileAgent的实际工具，再进行零Provider资格验证。本轮不复现两论文的效果数字，也不将它们的成功率作为Forge的直接基线。

## 已核对的来源

- CXXCrafter论文《An LLM-Based Agent for Automated C/C++ Open Source Software Building》，[arXiv:2505.21069](https://arxiv.org/abs/2505.21069)，§4、PDF第11–13页。知识库PDF SHA-256 `528a4579566965332ccb5bae5b4c42bca58e291d0727152d34c75f4f77b03efe`，通过knowledge_base读取，未复制Vault。
- CXXCrafter Community Edition，[commit bac70e99e48b210a350c18b3f93efd839787ce37](https://github.com/seclab-fudan/CXXCrafter-Community-Edition/tree/bac70e99e48b210a350c18b3f93efd839787ce37)。仅静态阅读，没有配置凭据或运行其Agent；公开社区版与论文原实验实现不能自动视为完全相同。
- CompileAgent《Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System》，[arXiv:2505.04254v1](https://arxiv.org/abs/2505.04254v1)，图2、§4.1–4.2、PDF第4–5页。知识库PDF SHA-256 `5da3da68d54c3441ec3e3771caef1aa8ebdd08b5a16b615e3c4f0e815c9947d5`。本轮论文HTML与GitHub名称搜索未定位到作者确认的实现，因此下述CompileAgent实现描述只依据论文。搜索结果中的`yuer-dsl/compileagent`是不同产品，不能误认论文实现。

## 工具到底做了什么

| 系统 | 确定性部分 | 内部仍需模型的部分 | 控制与反馈 |
| --- | --- | --- | --- |
| CXXCrafter | 文件名识别候选构建入口；环境架构/GPU探测；CCScanner提取高置信依赖；容器构建和日志收集 | 候选入口没有根入口时选择入口；相关文档选择与总结；生成和修订Dockerfile；论文的Judge | Parser→Generator→Executor反馈闭环 |
| CompileAgent | Docker/SSH Shell执行、目录树和文件/网页读取 | File Navigator的两SearchAgent讨论；Instruction Extractor中的SummarizeAgent；Website Search后的信息归纳；错误多Agent讨论 | MasterAgent通过提示规定工具顺序，失败先自行修复再讨论 |

CXXCrafter社区版的`parsing_module/utils/build_system_parser.py`按文件名遍历并取每系统浅层入口，存在根入口时返回首项，否则调用`llm_help_choose_build_system`。这不是对所有多入口都做语义判定。`environment_parser.py`用`platform.machine`、`shutil.which`与`nvidia-smi -L`观察环境；`dependency_parser.py`读取CCScanner `confidence=High`的名称和版本，并不等于已完成系统包安装映射；`doc_parser.py`先匹配文档文件名，再调用模型选文档并总结最多前三份。

CompileAgent论文第4–5页清楚指出：File Navigator是两个Agent讨论文件位置，Instruction Extractor使用SummarizeAgent并可请求文档URL；这两个“工具”不是零模型费用的静态解析器。Flow-based策略由提示连接工具顺序，不能等同于Forge持有权威状态和失效规则的确定性执行器。

## 对Forge的具体采用

继承“确定性候选提取→必要时语义处理→真实执行反馈”模式，先验证最小工具候选生成；不将命令模板或Workflow本身声称为新通用机制。复用已有PlanTask/BuildPlan、CanaryWorkflow、运行时、固定测试与clean replay。现有构建识别只解决识别/展示，不能直接生成带固定验证和交付依赖的完整BuildPlan；新模块只补这个缺口，不增加依赖。

工具不读取人工正确方案、历史成功命令、知识库或项目名称映射；输入为原源码树与任务固定身份/交付/验证。先支持单个根入口的Make、CMake、Autotools：

1. 识别入口并记录文件SHA、根目录名和选择理由。多入口冲突、缺根入口、其他构建系统、同名已有产物、同名交付歧义均请求Agent，不猜答案。
2. CMake使用`cmake -S . -B build -DBUILD_TESTING=ON`及`cmake --build build --parallel 2`；Make使用默认`make -j2`；Autotools已有configure则`sh ./configure`，否则从configure.ac/in用`autoreconf -fi`后配置、编译。脚本特殊bootstrap/自定义开关/外部依赖没有被解决，必须明确保留。
3. 系统逐字段装入原任务完整固定测试，不从验证命令反推配置，不重写Shell引号、不删改测试。这样同时改变了方案来源和测试装配接口；未来比较若要归因方案来源，模型方案也必须使用同一装配接口。
4. 暂存步骤在真实构建后按交付basename查找唯一ELF/ar普通文件；多匹配或无匹配失败。它是显式可重放的artifact_stage，不预先猜项目专用产物路径；最终结构、完整集合和哈希仍交原裁判。
5. 任何实际失败停在原Workflow交接，保存状态；本零Provider身份不执行模型恢复，不把“已有handoff”说成恢复成功。

## 资格问题与边界

固定buffer/Make、uncrustify/CMake、libverto/Autotools三个已见开发项目，一次候选、一次真实执行；不借用旧成功配方补齐失败，不替换项目，不重跑旧身份。重复静态生成确定性与拒绝条件由单元测试检查；容器结果区分候选生成、执行、固定测试、严格交付、replay和cleanup。模板失败也有研究信息，不要求3/3才允许保留主线，但只有实际闭合路径才能声明具备对应工程资格。

本轮零模型请求/Token/费用，不继承旧付费窗口。研究产物是工具方案可执行性与未覆盖情况；不能据3开发项目推断模型调用节省比例、成功率优势、自然恢复率或论文系统排名。保留C++边界：uncrustify本身是既有开发C++项目，其资格不扩大上一轮六C库的效果结论。
