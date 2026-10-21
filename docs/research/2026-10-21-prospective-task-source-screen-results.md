# 固定30项C++任务合同材料审阅结果

Issue #577；身份 `cpp-build-prospective-task-source-screen-v1`。本阶段完成只读材料采集与静态分析，为下一阶段参考构建定义任务；没有执行上游代码、Docker或付费Provider，没有新增方法效果。

## 观察及核验

沿用#571固定30项的完整原排名、精确commit与根tree，无重新搜索、替换、补位。30/30材料采集完成，0失败、0未观察；取得120个材料路径，1个超限未读取项：排名6 Matplot++ README.md为351588字节，超过预声明262144字节。其余材料照常保留，不能把该README当已读。

新采集器在开始前固定根文件名单、test/tests/testing/unittests/.github子树、首4个按字典序排列的workflow、每项目24路径上限；不递归读取全部源仓库或子模块，不访问外部文档。文档与workflow均为数据，不作为执行指令。30项事实摘要、114处原文件行号/原文/Git blob SHA/SHA256与待解义务见[完整逐项派生表](../../benchmarks/analyses/cpp-build-prospective-task-source-screen-v1-results.json)。每项均保持`task_qualified=false`、`holdout=false`、`build_result=not_observed`，没有把未取得材料记成无测试或平台不支持。

独立审计不导入采集器：核对类型化清单全部359文件、2715186字节、0链接；用真实`git mktree --missing`重建82个根/子树对象，并用`git hash-object`逐材料核验120份blob；核对父链、原30排名/commit、路径到树绑定、预设采集顺序及上限、base64与UTF8、运行release及组件快照、零上游执行记录。最终valid。首次独立审计错误地要求父API响应与格式化JSON字节完全一致，保留失败收据后改成结构及Git对象身份比较；没有修改原证据或重跑采集身份。

## 任务合同发现

排名16 `gatieme/CodingInterviews`的根Makefile不是编译配方：第58行`all:github`，第61行`github:`，第62–64行分别为`git add -A`、`git commit`及`git push origin master`。不能直接执行它来构建。这是一个实际来源中的入口歧义，支持今后把“文件名信号”与“真实编译动作”分开验证；不证明状态选择方法的收益，也不能据此认定该仓库深层所有题目都不可编译。

其他典型待解项是：Dobby测试依赖Capstone/Unicorn，四个测试程序含ARM仿真目标，不能因x86宿主直接跳过；rtorrent要求同版本libtorrent及CppUnit，不能让可选依赖缺失变成空测试成功；IWYU主干跟随Clang主干，必须固定工具链匹配及完整Python/CTest/CI测试边界。Beast与cxxopts主要库为INTERFACE，需先明确header-only任务的真实编译交付合同，不能拿临时示例冒充主库。

F3D有VTK9.4、LFS及渲染测试环境义务；YDB明确Yatool及至少80GB磁盘要求；ROS、GUI、GPU和深目录项目仍需补材料和资源审阅。上述均是任务定义待解项，不是实际构建失败，也不是永久排除依据。

## 下一参考定义工作队列

下表是**封存后人工审阅形成的任务定义工作顺序**，不是采集前冻结的最终样本，更不是已合格的五个任务。依据是Linux原生编译产品线索、直接作者测试程序/注册或完整测试目标线索及可追踪依赖义务；队列内保持原排名，不按工具模板覆盖、三策略效果或已知成功结果排序。其他25项继续pending，不改变原30项分母或补位。

| 原排名 | 仓库 | 原测试/端点线索 | 真实运行前首要待解项 |
| ---: | --- | --- | --- |
| 9 | arrayfire/arrayfire | Linux CPU后端、后端测试注册 | 主库端点、CPU配置、完整测试与数据/FFTW/BLAS/源图、资源 |
| 10 | rakshasa/rtorrent | Autotools、3套原测试程序 | 同版本libtorrent、CppUnit、完整断言/主端点/标准生成关系 |
| 14 | jmpews/Dobby | 共享/静态库、4个原测试程序 | Capstone/Unicorn、仿真与native测试真实断言/调用、完整源图 |
| 21 | YosysHQ/yosys | yosys主程序、unit及vanilla目标 | ABC/工具链/生成输入、完整测试图及既往暴露角色 |
| 30 | include-what-you-use/include-what-you-use | 主程序、单元/Python/CTest、Ubuntu CI | Clang主干匹配、资源目录、全部测试脚本及skip/CI范围 |

这些项目各有资源或语义风险，均未证明在当前运行预算内可行。选择它们进入定义工作不要求先出现自然失败，也不要求必须覆盖不同构建系统。排名6还只有下层测试委派且README未读；11渲染/LFS和子目录端点、22 header-only交付身份均待解，不能写成不合格。任务定义补充必须使用新采集身份，不能往已封存目录继续加文件。

下一环节先按此工作队列补齐精确源码/依赖图、完整原测试分母与断言、精确真实产物、功能配置及任务专属B生成关系。作者源码/测试/构建语义输入保持；允许正常生成文件须逐任务声明来源、路径、命令与新输出，不能复制已见libconfig白名单。参考执行另立新身份，实际完整测试、同镜像clean replay和cleanup通过后才标任务合格，再做三策略共同接口资格与结果前角色/费用/输入冻结。

## 证据与边界

- 运行release：`d5c354647ddb1a8dfdd00fda244680c4abad2279`；运行组件快照以raw中source-snapshot为准。
- manifest SHA256：`3324f12fd9c1a066076e62fd0d33ebf8d5c1ec5feb6022767143051456ba7ad6`。
- raw：`/home/yiwei/.codex/outputs/forge-prospective-task-source-screen-v1/`。
- inventory：`2facd675892ed07d7e98043a387e1e21c8e5956f0910f3d52a7f757bc050b967`。
- 父目录inventory：`88e23ea1b07465e613257ae57a2529086f4d427b557b50e470492ac95f5b1f9b`。
- 独立审计实现/收据、首失败、检查及发布收据：`/home/yiwei/.codex/outputs/forge-task-screening-session-2026-10-21/`。
- 协议：[预注册](../../benchmarks/preregistrations/cpp-build-prospective-task-source-screen-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-prospective-task-source-screen-v1.json)。

原目录有限精确名扫描4项命中/26项未命中保留；本轮新读取材料构成开发助手暴露，原commit API响应还含patch，不能声称严格盲、训练/全部历史未见或holdout。材料不自动注入实验Agent；未来所有策略对等披露的任务材料须另行冻结。静态审阅不是可编译率、自然恢复率或新总体效果。

新增6项测试通过；后端产品2322 passed、44 skipped、27 warnings及Ruff通过。前端lint/typecheck因当前环境未安装pnpm未执行，原始命令exit127留在会话日志，本次没有前端变更。结果提交后的三个相关CI必须全部通过才合科研依赖分支，实际发布状态以GitHub及会话收据为准，不进入main。旧失败、libconfig九槽、RQ3固定分母、P2和主线保持；用户HTML不动。本阶段0Provider/模型凭据/Token/费用/未知用量，没有续用过期付费授权。后续付费比较须在准备完成后取得新有效预算/时窗。
