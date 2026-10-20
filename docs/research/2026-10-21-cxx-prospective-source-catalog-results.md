# 前瞻C++来源目录：元数据阶段结果

Issue #571；身份`cpp-build-cxx-prospective-source-catalog-v1`。基础设施/样本准备，0Provider/模型凭据读取/Token/模型费/构建/Docker，无新方法效果。仅一次GitHub检索`language:C++ archived:false fork:false stars:500..5000`，stars降序第一页30项，完整响应与排名在逐项元数据请求前冻结；无重试/替换/补位。

30/30取得精确默认分支commit及根Git tree，0元数据失败、0未观察。标准库独立重建30个根Git tree对象SHA，逐条核对排名、条件、commit/tree链接、根文件信号，以及841份当前跟踪benchmarks/docs/research文件的SHA和精确owner/name暴露匹配，audit valid。有限扫描4项命中、26项未命中；后者不能称全部历史、训练/外部未见或最终holdout。

根文件信号非互斥：CMake19、Make2、Autotools1、Meson1；9项没有这些普通根文件信号。不按它们删样本或补位；这也不是跨构建系统均衡的最终评估队列。当前全部source_only_future_candidate、task_qualified=false、holdout=false，Linux适用、依赖闭合、真实编译端点、完整测试、归档对应、构建与交付仍未观察。

| 排名 | 仓库 | 精确commit前缀 | 普通根文件信号 | 当前跟踪精确名匹配 |
| ---: | --- | --- | --- | ---: |
| 1 | Nukem9/dlssg-to-fsr3 | 0e253f63c3c6 | cmake | 0 |
| 2 | paolo-projects/auto-unlocker | ddc03aa4a560 | cmake, make | 0 |
| 3 | Chlumsky/msdfgen | 1c106ed81178 | cmake | 0 |
| 4 | TixiaoShan/LIO-SAM | 0be1fbe6275f | cmake | 0 |
| 5 | gameplay3d/gameplay | 70c90a49dffd | cmake | 0 |
| 6 | alandefreitas/matplotplusplus | 2ccbb7ff8629 | cmake | 0 |
| 7 | begeekmyfriend/yasea | ed16739a8353 | 未识别 | 0 |
| 8 | anyrtcIO-Community/anyRTC-RTMP-OpenSource | 18e5314a5273 | 未识别 | 0 |
| 9 | arrayfire/arrayfire | ab4a5063c925 | cmake | 0 |
| 10 | rakshasa/rtorrent | d316b21cf02a | autotools | 0 |
| 11 | f3d-app/f3d | c6246720acf3 | cmake | 1 |
| 12 | spaceandtimefdn/blitzar | 1f0989de029a | 未识别 | 0 |
| 13 | wjakob/nanogui | e9ec8a1a9861 | cmake | 0 |
| 14 | jmpews/Dobby | 5dfc8546954c | cmake | 0 |
| 15 | clangen/musikcube | 9bc1234c8c36 | cmake | 0 |
| 16 | gatieme/CodingInterviews | a7fa3956c2b6 | make | 0 |
| 17 | ros-navigation/navigation2 | cea9ed9d2e55 | 未识别 | 0 |
| 18 | chromiumembedded/cef | 7f8a5ec28e93 | 未识别 | 0 |
| 19 | fritzing/fritzing-app | 5aa56a510183 | 未识别 | 0 |
| 20 | boostorg/beast | b4160b21f8aa | cmake | 0 |
| 21 | YosysHQ/yosys | 3718f7f135dc | cmake | 1 |
| 22 | jarro2783/cxxopts | bb791540908e | cmake, meson | 20 |
| 23 | CloudCompare/CloudCompare | dcc0fc41942e | cmake | 1 |
| 24 | MegEngine/MegEngine | 47952c075d86 | cmake | 0 |
| 25 | maximegmd/CyberEngineTweaks | 81d097e249d4 | 未识别 | 0 |
| 26 | dfranx/SHADERed | 780e96791fd8 | cmake | 0 |
| 27 | NVIDIA-Omniverse/PhysX | b97365c6ddb3 | 未识别 | 0 |
| 28 | ydb-platform/ydb | 87722879c952 | 未识别 | 0 |
| 29 | hku-mars/FAST-LIVO2 | 0d2c0346107b | cmake | 0 |
| 30 | include-what-you-use/include-what-you-use | c5625966cad2 | cmake | 0 |

未主动请求或解释候选README/源码、未生成参考、未执行候选；GitHub REST commits接口的完整原响应附带末次commit patch，30份响应均有此字段、合计2120817字节，保留在raw且未用于资格或方法调整。因此不能声称完全未取得任何代码字节、完全盲持出或训练未见。未来若需要严格无代码元数据通道，应使用ref和git/commits对象接口的新身份；本批冻结原响应不删除或重写。

运行release`6a22459106cfc89afdbbca3ac8cd7ddac2a39a40`，4组件，原UTC22:07:35截止不延长。raw `/home/yiwei/.codex/outputs/forge-cxx-prospective-source-catalog-v1`，inventory`88e23ea1b07465e613257ae57a2529086f4d427b557b50e470492ac95f5b1f9b`（69文件/0链接/3313566bytes）。独立实现/receipt、一次启动/终态和检查位于会话forge-cxx-continuous-session-2026-10-21/中的audit_prospective_catalog.py、prospective-catalog-independent-audit.json等。版本化目录表为benchmarks/analyses/cpp-build-cxx-prospective-source-catalog-v1-results.json；其数值只是元数据事实，不是可编译率。

新5回归及产品2287 passed/44 skipped/27 warnings、Ruff通过。结果HEAD三CI后仅合科研依赖分支，发布以GitHub和收据为准，不进main。下一步先按与模型outcome无关的Linux目标、真实端点、来源图和可固定完整测试资格确定最终队列与角色；不能从当前零模型正例挑相似样本，也不要求先找到失败才准入。生成文件写权限的待决边界见[任务合同复核](2026-10-21-source-contract-scope-decision.md)。旧失败、主线和RQ3旧分母保持，用户HTML不动。
