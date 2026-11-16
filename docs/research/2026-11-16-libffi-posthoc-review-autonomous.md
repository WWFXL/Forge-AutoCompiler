# 后验文件审查下的 libffi 单次自主构建

2026-11-16；Issue #768；真实模型采集与结果分析，结果待用户审核、未写论文。

## 结果

本次主库构建、静态/共享库交付、原始归档干净重建和清理全部通过，但恢复没有找到缺失开发包，而是新增兼容宏并最终固定检测值。记录为“构建与重建通过，语义审查待定”，不批准为正确修复经验。

| 指标 | 观察值 |
|---|---|
| 初始规划 | 7请求，13.77秒，0.0265275美元 |
| 三次恢复 | 12＋6＋6＝24请求，171.73秒，0.1228491美元 |
| 全程 | 31请求，408399Token，246.06秒 |
| 用量及保守估费 | 输入378558、输出29841；0.1493766美元；未知0 |
| 查询尝试／真实容器查询 | 23／19 |
| 主构建／交付／实际干净重建 | 通过／通过／通过 |
| 原输入与新增文件 | 454项原输入内容/权限/链接未变；189新增 |
| 文件与功能审查 | pending_review；新增宏退化，未批准复用 |
| 清理 | 成功；主/重建容器共4名称或ID实查不存在 |

估费按全输入缓存未命中0.30、输出1.20美元/百万Token，不代替账单。主产物为libffi.a与libffi.so.8.1.4，交付还含共享库链接；原始主构建任务不要求完整作者测试，不能把构建通过解释为测试或所有功能均正确。

## 方法与执行轨迹

身份`cpp-build-libffi-posthoc-review-flash-v1`，[预注册](../../benchmarks/preregistrations/cpp-build-libffi-posthoc-review-flash-v1.md)，运行revision `4bf06c9a5f484346ad71ec2331b0e639b0e5907f`。基于已合并的posthoc-review-v1，使用新默认简洁任务、P0规划工具约束＋规则路由＋R2通用依赖诊断＋恢复容器查询。Flash thinking low；未注入包名、旧成功命令、同项目经验或知识库。固定原libffi commit、归档及不可变镜像与此前观察相同。

1. 规划读取作者入口，提交`./autogen.sh && ./configure`、`make -j2`，首个命令因`LT_SYS_SYMBOL_USCORE`未定义退出1。
2. 第一次恢复搜索项目/系统宏并查询libtool包、版本及文件；本地无定义被错误解释为新版移除。Agent提交自建宏，拟通过编译foo并用nm检测下划线。但宏文本中的`rm -f`被仍保留的严格Shell删除约束拒绝，退出126；该宏命令没有执行。这是命令约束拒绝，不是后验原文件变化检查中止。
3. 第二次恢复改写宏，配置退出0，但`make`在文档目录因缺makeinfo退出2。该宏的检测安排本身也不能据其文字说明认定等价。
4. 第三次恢复查询texinfo，包索引显示未安装且无候选；使用作者公开的`--disable-docs`关闭文档生成，并再次改写兼容宏。配置及make默认目标通过；Workflow完成交付、原始归档干净重建与清理。

四份方案、三次交接、19次实际查询和全部执行命令见[轨迹](../../benchmarks/analyses/libffi-posthoc-review-2026-11-16/trajectory.json)。本轮首次使用了`package_search`，但仅按`libtool`查询，索引只返回libtool；`texinfo`也无候选。这些局部包索引结果不能证明所需组件不存在，Agent没有定位`libltdl-dev`或调用包文件提供者检索。工具可用与诊断完成仍有距离。

## 后验审查发现

454项原输入内容、权限与链接均与基线一致；C/C++实现与作者测试未改。189份新增包含正常Autotools输出、配置缓存、主库及一个Agent手写文件`m4/lt_sys_symbol_uscore_compat.m4`。最终手写宏核心为：

```m4
[lt_cv_sys_symbol_underscore=no
 AC_COMPILE_IFELSE([AC_LANG_PROGRAM([], [])], [:], [:])])
sys_symbol_underscore=$lt_cv_sys_symbol_underscore
```

两个编译分支均不更新检测值，结果实际固定为no。原configure.ac会据此决定`SYMBOL_UNDERSCORE`，所以这不是无关紧要的新文件；未改原文件也能改变配置语义。现有x86_64产物及重建通过没有证明该替代实现与原宏等价。原件`source_unchanged=true`与`source_review=pending_review`同时保留；[独立审查](../../benchmarks/analyses/libffi-posthoc-review-2026-11-16/source-review.json)明确不批准为已验证经验。本轮没有配置经验库，未把方案投放后续Agent；生成的verified-simple-recipe是运行候选证据，文件名不构成语义批准。

`--disable-docs`是作者公开的文档开关，符合主要库任务；没有删除测试或改动核心实现。相比之下，自造兼容宏需要单独解释和审查。本轮没有新增原输入变化，不能声称实际复现并越过了上一轮config.guess/config.sub的拦截点；该放行机制的直接证据仍是上一轮零Provider工程验证。

## 能够提取的研究信息

新策略下自主流程可以走完主构建及重建，但正确依赖诊断尚未解决。后验审查发现了“原文件未变、配置含义却被新增文件改变”的具体案例，说明文件变化记录需要与轨迹语义分析结合。

较上一轮54请求/0.2957706美元/497.67秒，本次请求、费用和时间较少，但前轮未完成、初始规划也独立生成，不能归因于策略改动或当成等任务降本。单个已暴露libffi不新增E57独立样本，不改旧失败，不自动写论文。

下一步建议围绕“找到真实提供者再修复”补足诊断：包索引无候选时核实索引覆盖及工具限制；优先安装真实宏提供者，避免以自造检测宏替代依赖。仅为建议，本轮不继续修改Harness或追加试验。

## 证据与结束状态

- [摘要](../../benchmarks/analyses/libffi-posthoc-review-2026-11-16/summary.json)、[分析说明](../../benchmarks/analyses/libffi-posthoc-review-2026-11-16/README.md)、[封存](../../benchmarks/analyses/libffi-posthoc-review-2026-11-16/seal.json)。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-posthoc-review-flash-2026-11-16-v1`；inventory SHA `95fd3887a3391f7421330ab9b2a7d9d3f1ddbe9dc9af7bfcd1ac47c33ea30b52`。
- 78份材料/实现快照核对运行revision一致；31请求/响应闭合、响应均deepseek-flash、逐次及Token费用复算一致；4个容器引用清理实查通过。
- 用户授权本次，自限1美元、UTC05:14:11—06:14:11；运行在05:20:20左右结束，无自动重试或追加Provider。单次额度已执行，无活动Provider。
- 不改核心系统、旧冻结材料或论文；发布以关联PR最新HEAD检查与科研集成分支合并记录为准。
