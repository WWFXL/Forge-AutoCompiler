# 自动配方溯源强接口真实探针结果

## 问题、身份与边界

Issue #504 / PR #505；独立身份`cpp-build-auto-provenance-probe-v1`，协议release a598925a，真实运行release 6eef2029。在父实验相关第二重复结果产生前固定libsndfile、buffer、libverto三项目/三系统/双重复/双臂12槽，但属于观察父第一重复后的后验选样，不称holdout。模型、固定完整功能测试、源码不变、精确交付、clean replay和cleanup保持原合同。工具臂允许批量操作，仅自动从权威Session选择成功build及有序recipe；不是预制构建答案。manifest SHA `ffcfff4244c2446441a7d1e7a6f20296279faced52df645e46a3c0480fcf8ff3`，65组件；旧父59组件未改。

此前同协议零Provider门禁6/6 strict，见`2026-10-20-build-auto-provenance-gate-results.md`。本批12/12观察完整、10/12 strict，0未知用量、全部cleanup成功；失败成本完整保留，不补跑、不调高预算。

## 完整结果

| 指标（包括失败） | plan | tool |
| --- | ---: | ---: |
| strict completed | 5/6 | 5/6 |
| Provider请求 | 37 | 50 |
| recorded tokens | 486546 | 508130 |
| 保守估算费用（美元） | 0.79509408 | 0.71376360 |
| Shell命令 | 28 | 40 |
| 单臂总耗时之和（秒） | 1095.568 | 840.297 |

plan请求少26.0%、Token少4.25%，费用却高约11.4%、耗时高约30.4%。这是固定三任务的实际完整路径描述，不是总体效果；不以成功子集挑选分母。四对共同成功、两对双方成功状态不一致，两个不一致均为libverto的不同重复。

下表为每项目每臂两重复均值，费用与耗时均含失败。

| 项目/臂 | strict | 请求 | Token | 费用美元 | 命令 | 耗时秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| libsndfile/plan | 2/2 | 6.5 | 89053 | 0.14407536 | 5 | 287.213 |
| libsndfile/tool | 2/2 | 9 | 108064.5 | 0.15068526 | 8 | 236.169 |
| buffer/plan | 2/2 | 2 | 14099.5 | 0.02660262 | 3.5 | 28.161 |
| buffer/tool | 2/2 | 4.5 | 30305.5 | 0.04221426 | 3 | 18.505 |
| libverto/plan | 1/2 | 10 | 140120.5 | 0.22686906 | 5.5 | 232.410 |
| libverto/tool | 1/2 | 11.5 | 115695 | 0.16398228 | 9 | 165.474 |

## 失败与轨迹解释

- libverto-r1-tool：12请求/139916 Token/$0.20124984后请求预算停止。10条Shell中前6条为diagnostic、其中5失败；之后依赖、配置、构建和固定6测试通过，但尚未暂存/submit/replay。不能称项目无法编译。源码、用量、cleanup闭合。
- libverto-r2-plan：初始`./configure --disable-shared --enable-static`后build成功，`make check`为0/6、exit2。真实触发1次handoff，但当前状态材料超过50000字节，`propose_with_context`在新恢复Provider调用前抛PlanContractError。9请求/137776 Token/$0.21852600，revision仍1、0修订、0 replay。功能测试失败与恢复上下文合同阻塞必须区分；未核验测试根因，不归为纯模型恢复失败。
- 其余plan交接均0；本批总计1次plan交接、0修订，不能证明状态修订有效。
- 五个成功tool臂各一次无参数submit/自动配方选择，无手工ID字段或额外参数、0 submit拒绝；失败tool无submit。全部成功plan也各一次submit，无拒绝。失败Shell合计8条，其中tool diagnostic7条、plan smoke1条；diagnostic失败不等于项目构建失败。

## 审计、验证与证据

raw：`/home/yiwei/.codex/outputs/forge-auto-provenance-real-v1/`；13618普通文件、64符号链接、499071439 bytes。inventory `d7bad477a8b355ffdbb21de127961c2f8f639798186d6c7d6ad0ecb27263e446`。独立审计`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/auto-provenance-real-v1-audit.json`为valid=true、issues=[]，核对inventory/组件/source/用量/测试/replay/cleanup及真实接口schema。

同目录`auto-provenance-real-v1-analysis.json`由冻结analyze纯函数只读生成；`auto-provenance-real-v1-trajectories.json`独立读取全部命令/submit/revision。未调用runner重跑，未修改任何冻结raw。相关19项测试、产品回归1929 passed/44 skipped、全量后端Ruff与517文件格式检查此前通过；结果提交后仍须最终head三项实际CI全SUCCESS才合并。

## 决定

强接口下plan仍减少请求，但没有固定任务合计费用或耗时优势；不把跨批差值解释为自动ID的因果效应，不作总体CI、非劣、自然恢复率、成熟Agent排名或第二创新点主张。总估算$1.50885768，低于阶段$6预留；共享已知估算累计$5.71180368，另旧live未知费用永久预留$1，预算占用$6.71180368，估算不是账单。

下一阶段为独立#506受控恢复资格，验证失败接管/修订/后缀失效在三系统真实执行中能否闭合。上下文50000字节问题保留为明确工程阻塞；如修复应另Issue/新身份，不回填本批成功。#507分层验证回顾分析独立发布，不用本批成功率替代其增量证据。
