# 简洁目标四方法48次比较准备完成

2026-11-04，Issue [#677](https://github.com/WWFXL/Forge-AutoCompiler/issues/677)。本轮是实验设计与执行准备，**0真实Provider调用、0新增模型费，48次正式结果全部未观察**。承接[#675核心接入](2026-11-04-simple-build-core-integration.md)，本轮集中固定样本和执行入口，未新增分类器、联网或多Agent组件。

## 已固定的论文比较

[协议](../../benchmarks/preregistrations/cpp-build-simple-system-comparison-flash-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-simple-system-comparison-flash-v1.json)、[共同任务与私有参考](../../benchmarks/fixtures/simple-system-comparison-v1/tasks.json)固定身份 `cpp-build-simple-system-comparison-flash-v1`。

|构建系统|项目|主要组件与作者测试|
|---|---|---|
|CMake|jsoncpp、miniz|原主库；从实际配置目录启动原完整CTest，串行且无测试报错|
|Make|pigz、highwayhash|pigz程序/原make test；highwayhash主库/原三个测试程序|
|Autotools|libite、libsrtp|原主库；原make check 21测试/原make runtest|

每项目两重复×基础Forge/经验Forge/强工具Agent/CXX社区参考，共48槽、每方法12槽。四Williams顺序使12块内各方法的位置和有向邻接均平衡。全部项目已有开发暴露，不称holdout；4C/2C++，不声称大型C++代表性。固定经验库12轨迹/8族/24条与六评价族隔离；库不更新，无本项目精确方案，无新增提炼。B-A回答跨项目经验增量；同项目复用独立研究，不混入本批。

共同公开任务保持简洁；主要组件参考、作者测试不送模型。主要构建与测试、交付、重放、完整完成分报，保留失败/超时/未观察。全部初始、读取、输出、失败、恢复及CXX所有Judge计费。到主构建时间增加包含初始规划/准备的新字段，避免把Workflow局部计时直接与工具Agent总计时比较。Forge另存初始规划/恢复时长；原生CXX不能拆出的阶段保持未知。

## 执行入口和边界

[`forge_simple_comparison.py`](../../scripts/forge_simple_comparison.py)接入现有四方法，统一Flash low/32768输出/禁自动重试，固定共同镜像、网络与2CPU；CXX继续保留原生工具/内部循环及Dockerfile重建差异，完整系统比较不当状态单变量因果。

`--prepare`/`--check-prepared`不读取凭据。`--run`先校验具体manifest SHA、身份、用户原答复、新确认/截止及费用上限，再注入现有DeepSeek环境接入。逐槽共享预算、停止整批的未知用量/模型身份/清理异常、普通失败保留后继续、意外中断不自动续跑均已接通。未闭合槽的费用不补零；结果中的已闭合费用只是小计。`--analyze`输出全分母、各层结果、逐槽时间/费用、初始/恢复请求与读取、经验检索次数。

拟授权共享10美元硬上限、确认起8小时；当前没有此新身份的付费授权。单槽1美元/96请求/100万recorded Token停止阈值，已发生末响应完整计量；总槽最多2700秒。保留Forge命令/Workflow内部预算与CXX原生预算差异，详见协议。工程准备不建立正式付费目录，不续旧账本或身份。

## 本轮实际验证

15项必要及相邻检查通过，覆盖48次分派、平衡顺序、经验仅进入经验臂、共同Flash/无自动重试、普通失败留存、未知/身份/清理停止、共享费用及中断未闭合记录，以及真实本机CTest对非标准构建目录的执行。Ruff/check与format通过；未重复旧资格链或本地产品全测，PR规定CI另行执行。

新增三项目各一次真实Docker独立参考，模型回复为离线脚本：

|项目|主要构建|作者测试|交付/干净重放/清理|本槽总秒|
|---|---|---|---|---|
|miniz（author-output目录）|通过|原CTest通过|全部通过|50.62|
|highwayhash|通过|原三个程序通过|全部通过|23.59|
|libsrtp|通过|原make runtest通过|全部通过|55.23|

各1次模拟模型响应，真实Provider/Token/费用均0；原源码保持。六个compile/replay容器的名称/ID共12项实际检查均不存在。jsoncpp/pigz/libite沿用#675已有真实路径，不重跑、不把两批拼成方法成功率。三条参考支持新任务/作者入口可运行，不证明Flash会生成这些方案或新版方法有效。

原件：`/home/yiwei/.codex/outputs/forge-simple-comparison-preparation-2026-11-04-v1/`，含driver、逐组工作树代码快照、公开任务/私有参考、请求/回复、命令、结果、launch.log和resource-check.json。driver保存的是运行时工作树，不以最终发布revision冒充早期快照；后续批分析/文档改动与核心计时改动区分。

## 下一步

最终PR通过CI后仅合科研集成分支，知识库同步当前准备身份；实际head/merge、候选SHA、CI和知识库SHA以本会话发布收据为准。获得新预算/时窗后直接运行固定48次，不再扩一轮组件。若模型服务失败或遇停止条件，保留正式失败和未观察，再分析已获得证据。旧E01/E30/E33/E35–E41与论文v0.6继续按原版本使用，本轮不新增效果编号。

本轮早期发布曾阻塞：原生Git默认、HTTP/1.1及TLS兼容尝试均被`gnutls_handshake()`断开，当时远端新分支404、PR未创建。首次阻塞收据保留；它不代表后续发布状态。

发布恢复决定：现有用户授权已经覆盖推送、PR和检查后合并，无需重复审批同一内容；本轮明确启用Git Data API备用路径，保留原生失败收据，逐blob/tree核对内容，随后按原分支完成PR/CI。最终远端提交、检查和合并状态另存发布收据，不以此决定本身宣称成功。

PR [#678](https://github.com/WWFXL/Forge-AutoCompiler/pull/678)已创建，初始提交`23e615c82c4c85c1e8b8e7e9edebea64c2ee8c6f`的远端commit/tree与本地一致。首轮CI的两项冻结检查通过；后端为2712通过、46跳过、1失败，原因是新增的离线分派测试错误读取本服务器历史经验文件。测试已改用临时空经验夹具，相关15项和Ruff再次通过；正式经验库、173个运行组件及manifest SHA均不变。该失败只涉及测试环境独立性，不是一次模型实验失败；新HEAD检查全部通过后才合科研集成分支，最终状态见发布收据。
