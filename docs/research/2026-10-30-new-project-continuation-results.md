# 新项目系统比较：原未启动24槽的独立续段结果

本批24/24槽实际终结，17完整、7未完整，0中断、0未观察。Forge/强工具/CXX社区参考完整6/8、5/8、6/8，新增268请求、3888815 recorded Token、保守估费$1.3823835。论文证据编号[E33](THESIS_EVIDENCE_INDEX.md#e33)。主要同判定比较为Forge／强工具：五组共同成功任务中Forge估费低15.4%、时间高3.4%；保留收益和取舍。

## 问题、设计与方法

身份`cpp-build-new-project-system-continuation-flash-v1`，检验模型规划＋状态Workflow＋失败Agent，相对强工具Agent有什么完整完成、模型费用和时间取舍；CXXCrafter社区版作为外部实现参考。按[预注册](../../benchmarks/preregistrations/cpp-build-new-project-system-continuation-flash-v1.md)及[manifest](../../benchmarks/manifests/cpp-build-new-project-system-continuation-flash-v1.json)，精确执行父排期原19–42个未启动槽，三方法各8槽。FSE有两重复，其余六项目各一次；新槽到原槽的映射保存在协议与逐槽CSV，不把这些重复当独立项目。

本批不是补跑旧失败或第18中断槽。父身份[E32](THESIS_EVIDENCE_INDEX.md#e32)的17原终态、1中断、24未观察及42分母保持；跨身份只能描述性合列，不能写成原42槽单一身份全部完成。先前部分成绩与任务准备已见，有限Git检索仅支持“新于当前方法调试”，不称盲holdout、训练未见或随机项目总体。

三方统一deepseek-flash thinking low、公开完整任务、冻结源码与依赖资源、CMake Release及两作业环境，初始读取、规划、输出、格式纠错、失败、恢复及CXX内部Judge全部计费。Forge模型只读生成阶段方案，Workflow执行，并在有显式作者BOOL目标时观察实际配置、必要时直接修订或交接Agent；强工具Agent使用共同任务与提交Harness，自行选择工具和构建动作。Make/Autotools仍是普通Workflow＋失败Agent，不冒称使用CMake配置增强。

CXX保留社区版Parser/Generator/Modifier/Judge与最多十版Dockerfile；外部失败不回其Modifier，工具、原生循环、CPU affinity与Forge quota实现不同。本次进一步发现默认executable smoke差异，因此主要同判定比较为Forge／强工具，不把三方结果当完全同裁判排名或论文原版排名。

固定任务包括jsoncpp全套串行测试、PEGTL的128CTest和37默认示例、inja完整原测试与benchmark、highwayhash原三测试程序、libsigcplusplus实际32PASS、libsrtp原完整runtest和FSE默认fuzzer。原源码、原测试与已有输入不可改，允许正常新增生成文件；完整交付仍要求精确产物与同镜像干净重放、源码／链接保持及清理。

## 固定24槽主表

| 方法 | 计划/观察 | 完整 | 未完整 | 请求 | 全部估费/美元 | 累计分钟 |
|---|---:|---:|---:|---:|---:|---:|
|Forge状态Workflow|8/8|6|2|38|0.2411922|31.23|
|强工具Agent|8/8|5|3|175|0.8869458|54.70|
|CXXCrafter社区版（参考）|8/8|6|2|55|0.2542455|77.45|

全部槽中Forge相对强工具估费低72.8%，累计时间低42.9%，完整数多1；但两方完整数不同，且FSE恢复与libsigcplusplus失败开销影响很大，不能把总费差当共同成功任务的单位效率或纯状态因果。0中断、0未观察、0缺失计时、0未知用量。CXX未完整包括1个外部裁判启动错误，不作同裁判排名。

## 逐项目与共同成功配对

| 项目/重复 | Forge | 强工具 | CXX参考 |
|---|---|---|---|
|fse/r1|未完整；5请求；$0.0469434|未完整；41请求；$0.1865982|未完整；6请求；$0.0155916|
|jsoncpp/r2|完整；6请求；$0.0306597|完整；8请求；$0.0329649|完整；6请求；$0.0254670|
|pegtl/r2|完整；1请求；$0.0075795|完整；7请求；$0.0406617|完整；9请求；$0.0642387|
|inja/r2|完整；3请求；$0.0163068|完整；8请求；$0.0384393|完整；7请求；$0.0541323|
|highwayhash/r2|完整；7请求；$0.0356307|完整；4请求；$0.0177843|完整；6请求；$0.0183591|
|libsigcplusplus/r2|完整；4请求；$0.0274215|未完整；50请求；$0.2578692|完整；6请求；$0.0192897|
|libsrtp/r2|完整；9请求；$0.0504528|完整；7请求；$0.036426|未完整；9请求；$0.0346410|
|fse/r2|未完整；3请求；$0.0261978|未完整；50请求；$0.2762022|完整；6请求；$0.0225261|

Forge与强工具共同完整的5组为jsoncpp、PEGTL、inja、highwayhash、libsrtp。该子集按完成结果条件化，仅辅助解释效率，不替代固定24槽主表：

| 方法 | 共同完整 | 请求 | 估费/美元 | 累计分钟 |
|---|---:|---:|---:|---:|
|Forge状态Workflow|5/5|26|0.1406295|12.15|
|强工具Agent|5/5|34|0.1662762|11.76|

共同成功子集中Forge估费低15.4%，时间高3.4%；这是费用收益与时间取舍，并非所有指标占优。highwayhash、libsrtp的Forge估费均高于强工具；jsoncpp、highwayhash、libsrtp时间也更长。三方共同完成4组的辅助数值保留在JSON，CXX判定差异仍不能由成功子集消除。

## 构建系统与语言分层

每格为“完整/计划；全部估费美元；累计分钟”；Make包括两次FSE，不能当三个独立项目。

| 分层 | Forge | 强工具 | CXX参考 |
|---|---|---|---|
|autotools|2/2；$0.0778743；4.84|1/2；$0.2942952；8.84|1/2；$0.0539307；10.65|
|cmake|3/3；$0.0545460；9.44|3/3；$0.1120659；9.69|3/3；$0.1438380；32.14|
|make|1/3；$0.1087719；16.95|1/3；$0.4805847；36.17|2/3；$0.0564768；34.66|
|C|1/3；$0.1235940；17.78|1/3；$0.4992264；36.98|1/3；$0.0727587；37.95|
|C++|5/5；$0.1175982；13.45|4/5；$0.3877194；17.71|5/5；$0.1814868；39.49|

## 初始规划、状态与恢复

| Forge费用阶段 | 请求 | 估费/美元 |
|---|---:|---:|
|初始规划（含读取与纠错）|33|0.1859694|
|失败恢复|5|0.0552228|

全部8份自然初始方案已登记原路径、SHA、状态及费用，无按结果筛选。初始规划平均4.125请求、$0.02324618，并非一次规划必然只需一次模型请求。六槽无需恢复即完整；两个FSE槽共3个恢复episode、5请求，均未完整。六次CMake配置观测全部satisfied，直接配置修订0；Make/Autotools无此配置观察，不把未观察写为满足。

这些数据支持本批完整系统的费用/时间取舍，不能证明未触发的配置直接动作有增量。组件效果仍独立引用E01；本批FSE恢复没有得到新的完整完成，也不能据此否定其他错误上的恢复价值。

## RQ3：固定分母的原轨迹分层

每格为“通过/拒绝/未观察”；末次固定复合检查可能因超时、输出约束或新构建使旧测试失效，不等于作者测试叶出现功能失败。

| 层次 | Forge | 强工具 | CXX参考 |
|---|---:|---:|---:|
|最终固定任务复合检查|8/0/0|6/1/1|7/0/1|
|末次有效原测试合同|8/0/0|6/1/1|7/0/1|
|精确交付路径集合|8/0/0|8/0/0|7/0/1|
|完整clean replay|6/0/2|5/1/2|6/1/1|
|原源码与链接保持|8/0/0|8/0/0|7/0/1|
|原尝试清理|8/0/0|8/0/0|8/0/0|

强工具FSE首重复末次固定测试超时记拒绝；第二重复曾三次通过完整测试，但后续build使旧测试不再覆盖最终产物，最终记未观察。两者都保留此前通过记录。CXX/libsrtp的外部检查未启动，相关层均未观察；清理成功不能反推其他层。交付路径集合层单独核对实际文件，不能代替产物结构、smoke或整个提交验收。

默认executable smoke另列，四项依次为“通过/拒绝/未观察/不适用”：

- Forge状态Workflow：2/2/0/4。

- 强工具Agent：2/2/0/4。

- CXXCrafter社区版（参考）：0/0/5/3。

该分层是本批观察的解释，不估总体误接受/误拒绝率；固定原数字及所有失败保持。

## 失败案例与裁判边界

FSE首个Forge槽通过固定原测试后，被提交端默认`-version`、`--version`、`--help`三个参数拒绝。同一交付ELF的原生`-V`和`-H`只读诊断均返回0，源码`programs/commandline.c:165–166`明确支持它们；`-h`不是帮助参数。这是默认smoke适配问题，不能写成项目编译失败或原作者测试失败。诊断无Provider、无新构建，文件SHA未变；不将事后诊断回填为原在线完成。

共享CXX执行器`scripts/forge_cxx_current_reference.py:external_check`执行固定原测试、源码与精确产物结构等检查，但没有执行Forge提交端额外默认executable smoke。此差异也影响E30／E32可作出的比较主张，两份旧报告仅增加解释更正，原数字和冻结证据保持。静态库无需该可执行smoke；CXX可执行产物的这一额外层记未观察，不能填通过。

FSE首个CXX槽的原构建及重放均通过原测试、源码与交付结构检查，但原始产物嵌入`Oct 29 2026`，重放嵌入`Oct 30 2026`。源码`programs/commandline.c:73`使用`__DATE__`；两个145008字节文件有22字节不同，精确字节重放因此未通过。原SHA为`e4b0522b0c4a9bbae6c36492bc2d2a7d517e4bfb8b2fc36405e8543bb2b8f6b0`，重放为`13eeb469beea05bda9a6c257c4ac05b69bb60281a55f9f754f6bece9f64098e6`。这是功能测试通过后仍存在复现差异的具体案例；本批没有临时加入`SOURCE_DATE_EPOCH`、修改源码或改变判定。

libsigcplusplus强工具槽17在原工作区通过原32测试并暂存交付，但两次clean replay均`recipe_execution_failed`。安装mm-common等的复合命令虽然产生副作用，后置`pkg-config --modversion mm-common`失败，使安装命令整体exit1、被成功配方筛选排除；后续原环境`autogen.sh`成功不等于重放环境已具备依赖。最终`GraphRecursionError`终结，50请求、810022 Token、$0.2578692均计入，源码保持与清理通过。这是与父批同项目相近机制的再次观察，不当跨项目总体因果，也不把Harness配方限制全部归为Agent推理能力。

libsrtp的CXX槽20原生循环报告成功，但`external_check`把2382项、324179字节的完整源码哈希JSON作为单个进程参数传给Docker，触发`OSError: [Errno 7] Argument list too long: 'docker'`，外部测试尚未启动。原生成功不能代替固定任务成功；本槽保留未完整与验收基础设施错误，源码、原测试、精确交付和重放均未观察，不填失败，不归于CXX项目构建能力。清理成功与验收未观察分别记录，本批没有修裁判后补跑。

FSE首Forge槽两轮恢复后`budget_exhausted`终结；第二Forge槽以“无变化修订不能触发相同失败的重复执行”的`PlanContractError`终结。强工具首FSE槽41请求后节点时限终结，第二FSE槽50请求后`GraphRecursionError`终结；这不是10美元额度耗尽。FSE第二CXX槽在同日构建与重放字节一致，原始完整结果保留；它没有经过Forge额外默认smoke，不能将该完成数差异当方法优势。

## 证据与后续

原始证据目录为`/home/yiwei/.codex/outputs/forge-new-project-system-continuation-flash-v1`；操作会话`/home/yiwei/.codex/outputs/forge-new-project-continuation-session-2026-10-29`保存授权、启动与费用账本、诊断和发布收据。只读提取器、逐槽CSV及版本化详细分析在`benchmarks/analyses/`同身份下，诊断另列为事后只读分析，不作为新模型效果。

授权新增模型费用最多10美元，UTC2026-10-29 15:20:28至23:20:28（北京时间29日23:20:28至30日07:20:28），准备计入；无自动重试、不补槽，未知用量／模型身份异常／清理失败停止整批。估费按输入0.30／输出1.20美元每百万Token、输入全部按缓存未命中计，非实际账单。原运行release为`c71ff9d980dd6aab24859db4c4d570eb3cb902bc`，候选SHA为`182cd9bad1a59d96c8a43dde590e402c6ea296cd858676203bddedb4cb94f661`。

正式运行UTC2026-10-29 15:21:44至18:05:24，正常退出，账本已闭合，未触发整批停止。封存57269普通文件／5链接／558453249字节，inventory `91c1763a49a3568a6c2c2d7ea5925437c05d70d62cc922a14fa10af6bf089480`。原响应用量、费用、模型身份、350冻结组件、24槽排期和351个实际容器name/ID不存在的一次本批只读核对通过；提取器的24项逐槽计量核对通过，没有重跑旧资格链或产品全测。原始大文件仍在本机，未建立异地备份。

- [详细分析](../../benchmarks/analyses/cpp-build-new-project-system-continuation-flash-v1-results.json)保存固定分母、各分层、全部自然初始方案及原始指针。
- [逐槽CSV](../../benchmarks/analyses/cpp-build-new-project-system-continuation-flash-v1-slots.csv)与[只读提取器](../../benchmarks/analyses/cpp-build-new-project-system-continuation-flash-v1-extract.py)支持复算。
- [FSE默认smoke诊断](../../benchmarks/analyses/cpp-build-new-project-system-continuation-flash-v1-fse-smoke-diagnostic.json)、[跨日期字节诊断](../../benchmarks/analyses/cpp-build-new-project-system-continuation-flash-v1-fse-replay-date-diagnostic.json)、[libsrtp裁判传递诊断](../../benchmarks/analyses/cpp-build-new-project-system-continuation-flash-v1-libsrtp-cxx-evaluator-transport-diagnostic.json)均0新增Provider，保留事后分析身份。

本批系统结果与E01固定初始方案消融、E04恢复开关分别解释，不从系统成本差异推断未触发的配置动作收益。后续优先组织完整论文结果，同时独立设计共同可执行功能oracle和固定时间环境，保持原源码／原测试与精确字节标准；新版本比较另定身份，不以余款自动扩本批，也不回填当前失败。无需重新执行旧参考资格链或产品全测。
