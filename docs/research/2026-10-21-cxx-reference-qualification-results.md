# 新增C++来源图与完整参考任务资格

Issue #554，PR #555。本轮是**样本资格与基础设施**，目的是补齐#552主要为C库的范围，尚无新模型效果。研究主线继续为“面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究”，不以所有指标胜出为继续条件。

## 固定来源与暴露

在读取新源码/观察构建前固定以下三项，不替换候选。全部CMake，不能据此宣称新增跨构建系统覆盖或大型C++泛化。

| 项目 | 完整主commit | 主归档普通文件/C++源扩展文件数 | 来源图 |
| --- | --- | --- | --- |
| jbeder/yaml-cpp | c5e65360373d1d99d6b6848c991cd4fcee435009 | 404/160 | 自带GoogleTest 1.16.0，无gitlink |
| simdutf/simdutf | 8d82299606e675b50de8dc16fd118aae4b65bfde | 763/287 | 无gitlink |
| google/snappy | 9c28114a38866f6deeaa826db918293bc28ae410 | 53/11 | 补齐两个上游gitlink后489普通文件 |

C++计数仅按.cpp/.cc/.cxx/.c++扩展，yaml-cpp主归档包含vendored测试，不以文件数衡量研究贡献。snappy的third_party/benchmark固定b20cea674170b2ba45da0dfaf03953cdea473d0d、third_party/googletest固定b796f7d44681514f58a683a3a71ff17c94edb0c1；URL来自原.gitmodules，commit与完整Git tree逐项核对。未用系统GoogleTest替代，保留默认benchmark构建。

来源采集先冻结全部HEAD，再每项一次codeload归档；只读检查，不执行来源命令。复用既有边界检查与normalized_source，仅剥外层目录、将依赖归档装入固定gitlink目录，保存所有普通文件hash。组合归档不冒充纯主commit的git archive。独立stdlib实现复算原归档每个普通文件、主commit、gitlink、组合tar及hash索引均一致。

本机当时可达Git历史及指定c411d52a/915a6d67两树的benchmarks/docs/research精确owner/name检索均无命中；不证明训练、外部任务、别名或全语义历史未见。读取来源和人工参考后，已对开发助手产生设计暴露；后续应表述为新增项目的前瞻模型评估，不能称完全holdout。三个仓库metadata均fork=false，不构成代码亲缘独立证明。yaml-cpp/snappy共用GoogleTest测试基础设施，后续登记该关联，不将三个owner直接当三个独立统计家族。

## 首批参考观察：2/3获得资格

身份cpp-build-cxx-reference-qualification-v1，运行release c4b8f8461310adff21affd0bb0183a574213241a，manifest SHA256 33e3ff7ad9949b30ab3e2a533b124cc57bae474383fd2c6d4347f4f9117a5d22，132冻结组件。

| 项目 | 首轮与干净重放作者测试 | 交付/replay/源码/cleanup | 观察 |
| --- | --- | --- | --- |
| yaml-cpp | 两次均1068个默认GoogleTest通过，CTest 3/3 | 全通过 | qualified=true，172.883秒 |
| simdutf | CTest未观察；编译已通过 | 交付/replay未观察，源码/cleanup通过 | 配置缓存类型断言拒绝，94.068秒 |
| snappy | 两次均25个默认GoogleTest通过，CTest 1/1 | 全通过 | qualified=true，152.598秒 |

yaml-cpp上游默认8个DISABLED测试、snappy默认1个DISABLED测试均保留记录；1068/25只指实际默认执行数，不把禁用用例填成通过。未传GoogleTest过滤器，未关闭作者默认测试。snappy安装zlib/lzo2/lz4开发依赖，固定检查三项HAVE_LIB*=1，并构建默认snappy_benchmark；未把运行性能benchmark作为正确性测试。

simdutf失败为**本轮人工参考检查错误**：configure传-DBUILD_SHARED_LIBS=OFF，CMakeCache实际为BUILD_SHARED_LIBS:UNINITIALIZED=OFF，而固定smoke在CTest前断言BOOL类型，Python AssertionError/exit1。SIMDUTF_TESTS/BUILD_TESTING/TOOLS=ON、FAST_TESTS=OFF均已在cache正确记录，编译exit0。不能把它称上游CTest失败、模型恢复失败或项目不可编译。max_handoffs=0使Workflow将失败分类为budget_exhausted，剩余1710秒，不能解释为时间预算耗尽。

这也提示后续正式任务需审阅配置检查的领域含义：功能选项和真实静态交付是任务要求，缓存类型字符串本身不是方法收益。不得把检查夹具错误包装成自然构建难题，也不得在已冻结批次修改裁判挽救结果。

## 独立缓存类型资格

身份cpp-build-cxx-reference-cache-qualification-v1，仅复制父simdutf任务，将唯一configure参数显式写成-DBUILD_SHARED_LIBS:BOOL=OFF。OFF语义、固定smoke全部字节、作者默认完整CTest、FAST_TESTS=OFF、源码图、镜像、交付与资源保持；不是在旧身份重试，不回填首批结果。

运行release 5d25c82573c3fa210f40d90a1cbfd546ee9543a3、135组件，manifest SHA256 eb56210d86936b3d6f9eabfa6c55b89cafc49f13b89683992c15b20a9cee3eb1。独立执行completed，428.679秒；原/replay交付、源码与实际cleanup均过，独立audit valid=true。两次CTest均94注册、93通过/0失败/1跳过：check_feature_macros调用git ls-files失败，因为来源归档无.git，按上游SKIP_RETURN_CODE=142跳过。CTest汇总100%不代表94项实际全通过，不将该项目直接列为无跳过完整测试资格。

下一独立cpp-build-cxx-reference-metadata-qualification-v1只在最初dependency追加git init -q与git add --force --all，准备精确原源码的本地索引，不创建伪commit、不改原源码/配置/测试或SKIP_RETURN_CODE。要求该检查在原/replay真正Passed且无CTest跳过。138组件，manifest SHA256 27a0429ad9eb8f97685332821a97c9efd58d945f579573e50cbc6da39dc45881；该身份dependency阶段Git exit128：root容器拒绝宿主用户拥有的挂载目录（dubious ownership），未进入configure/build/CTest/交付/replay；原源码和实际cleanup通过。库存28ff9d2e7d68dc8be1f2ae2db20ec4d3bb7a7f47e61f373e1b6b64ff75cd762e。此准备失败单独保留，不与父身份混算。

## Git元数据资格v2与最终可用任务池

新身份cpp-build-cxx-reference-metadata-qualification-v2只在v1的git init/add之间加入`git config --global --add safe.directory /workspace/repo`。仅信任临时原执行/replay容器的精确目录，不使用通配符、不改宿主Git配置、不创建伪commit；原源码、固定测试、预算和截止不变。

运行release 740d974f786f9d0531bb14ef6bd0e512461c1e93，141组件，manifest SHA256 fbe4caa8928c0f442bf707394d6a8d1dda159fed0f1824cb2f21d12d3ede2055。独立执行completed，430.917秒；原工作区及clean replay均94/94 CTest实际Passed、0失败、0跳过，check_feature_macros真正Passed。原源码全部普通文件不变、Git索引集合与原来源hash索引相同、精确静态交付及原/replay hash相同、所有原与重放容器实际不存在，独立stdlib主审计及父链/测试详情审计均valid=true。宿主只读详情审计首次亦受Git所有权保护拒绝，保留失败脚本/收据后改用单进程精确`git -c safe.directory=<source>`读取；没有改raw、裁判或宿主配置。

最终可用于下一阶段的参考任务为yaml-cpp/snappy（原三槽身份）及simdutf（metadata-v2）。这是跨明确修订身份的**任务资格池**，不是原v1三项全过，不合并为方法成功率。所有前序失败/跳过均保留。该结果支持固定来源和严格任务可复现，不支持真实模型策略效果。

## 统一边界与检查

全部使用镜像sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a、2CPU，单项32命令/0handoff/方案1800秒/单命令900秒/replay1200秒。新项保留3300秒，截止UTC2026-10-20T18:19:33Z（北京时间2026-10-21 02:19:33）不延长。固定顺序、失败不替换、不自动重试，cleanup不闭合则停批。

原源码全部普通文件不变，精确交付至少真实ar，原/replay集合/类型/大小/hash一致，原与重放容器实际不存在才完成。引用“完整测试”均指该固定配置下作者注册的默认测试，不代表全部平台/可选feature矩阵。凭据读取、Provider、模型Token/估费/未知用量均0，不继承#552预算另开付费身份。参考v1入口exit0表示三槽完整终结，不能替代逐项目qualified判断。

新增17项身份/来源图/类型修正边界回归；含旧来源/参考相关合计33项。产品2158 passed/44 skipped/27 warnings，Ruff通过。历史pytest临时目录权限清理告警保留，未清理其他任务目录。124个#552历史组件及132/135/138/141个各参考身份组件逐hash保持；用户HTML SHA256 7722b81a4a3d6d52d5ddbc59ef9a67910ea1231f130c8e765cb584cff9790325未改。

## 静态模板与下一步

未执行模板、未调用模型的静态检查：yaml-cpp/snappy因并列BUILD.bazel/CMakeLists.txt被现有单根模板拒绝；simdutf生成构建候选。这是候选生成/拒答记录，不是构建成功、模板自然覆盖率或收益。后续若保留三策略，应单列初始拒绝升级与运行中失败恢复；两模板拒答项目工具路径会进入与模型路径相同的初始Agent，不能把随机轨迹差说成消除规划。

保持当前实现作基线，不在本批优化并列构建入口或重复读取。参考资格结束后，再固定C++前瞻评估角色、关联组、方法顺序、共享测试/装配/恢复及全费用，准备独立公平比较（18槽顺序草案见同日cxx-next-comparison-design.md，尚未冻结/准入）；真实比较须有效新身份/预算/时窗，不自动调用Provider。未来检查若需改进必须在新结果前冻结同等任务，不按方法结果改裁判。不加P2、不改RQ3固定分母，不改研究主线。

## 证据入口

以下raw均为新create-once身份，原#552及更早证据保持只读：

| 目录（/home/yiwei/.codex/outputs/下） | inventory canonical SHA256 | 文件/链接/bytes |
| --- | --- | --- |
| forge-cxx-source-qualification-v1 | a8c8936fe51abc525ce4076fe1ee1195ab20388e2ec6df6ffd4d16c43f186b7c | 27/0/6420522 |
| forge-cxx-reference-inputs-v1 | 8b4b6661314a9be96b5e30f73bdbe47fcea3932ffa8fc3e9cb1814adb1031734 | 149/0/29294221 |
| forge-cxx-reference-qualification-v1 | b57011899a6ffae3c915c4203a0e488a109442519c1ddaa604e59f5ee3820501 | 5534/1/252845583 |
| forge-cxx-reference-cache-qualification-v1 | c2573fa60ee4cbaf7c8b5695da1d07d3614ab01432cbb32a7fa8d6f0f3c48095 | 4519/2/231228645 |
| forge-cxx-reference-metadata-qualification-v1 | 28ff9d2e7d68dc8be1f2ae2db20ec4d3bb7a7f47e61f373e1b6b64ff75cd762e | 929/0/23347816 |
| forge-cxx-reference-metadata-qualification-v2 | 2c0d214ce30a292e9b16599b4b4ff23cb26ed3a9db41fb18609f30eea4b3479b | 6071/2/237461516 |

独立来源、全部参考身份、最终父链与实际测试详情审计均valid=true。执行/校验/静态模板/审计源码与收据统一在/home/yiwei/.codex/outputs/forge-cxx-qualification-session-2026-10-20/：independent_audit.py、independent-source-audit.json、independent-reference-v1-audit.json、frozen-component-audit.json、static_template_audit.py、static-template-audit.json、unique-launch.json、unique-cache-launch.json、unique-metadata-launch.json、unique-metadata-v2-launch.json、independent-metadata-v1-audit.json、independent-metadata-v2-audit.json及completion-detail-audit.json。最终逐hash/实际零容器/零费用审计见final-qualification-boundary.json。协议均在benchmarks/manifests与preregistrations对应同名文件。

最终结果HEAD三项CI、PR555合入科研依赖分支、Issue554关闭和知识库同步以GitHub及本会话最终发布/知识库收据为准，不进入main；#470长期总跟踪保持OPEN。
