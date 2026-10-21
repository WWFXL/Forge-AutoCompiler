# rtorrent 实际通用模板执行与恢复资格

跟踪 #585，承接 #583。工程资格已完成观察，唯一槽未严格完成；0 Provider、凭据、真实 Token、模型费用或未知用量。没有真实模型策略效果。主线仍为“面向 C/C++ 仓库自动化构建的状态感知动作选择与验证方法研究”。

## 新证据

新身份 `cpp-build-rtorrent-actual-template-gate-v1` 的初始方案来自实际 `boundary_tool_actions`：`autoreconf -fi → sh ./configure → make -j2`。初始0脚本响应，无模板拒答，未读人工参考。前瞻接纳已校准的-fi/-ivf及标准configure日志config.log；818原文件、40精确生成SHA及全部验收保持。

实际bootstrap退出0；根configure退出1，明确报告 `Package 'libtorrent', required by 'virtual:world', not found`，同一日志的文件边界检查通过。Workflow从权威执行记录触发configure阶段交接。这建立了本任务通用单根模板的具体局限：它未安排仓库附带libtorrent源码依赖的构建/安装，而不是仅命令形式不符导致拒答。

仅在交接后提供一次明确标记的脚本完整参考修订，revision2真实执行 `rm -f -- config.log` 成功，随后 `cd vendor-libtorrent && autoreconf -ivf` 被原生成SHA规则拒绝。日志显示libtoolize选择父目录 `..` 为辅助目录。独立对照四个生成文件：`vendor-libtorrent/{Makefile.in,src/Makefile.in,test/Makefile.in,configure}` 的辅助路径从本目录转到父目录（具体逐行diff在派生结果）。这支持生成顺序/既有父目录辅助文件影响实际输出的诊断；没有运行独立顺序反事实，因此不声称已完整定位因果或该差异导致功能错误。

依赖bootstrap失败后第二次交接进入一次恢复门禁，被停止；只有一次agent.started和一次脚本响应，不存在第二次模型调用。首方案成功bootstrap未作为修订成功前缀保留，只保留共同源码准备，不主张增量恢复节省。

| 层次 | 观察 |
| --- | --- |
| 实际模板准入与主bootstrap | 通过，初始0脚本响应 |
| 根configure | 真实依赖缺失失败，边界通过 |
| 权威交接/脚本修订/日志清理 | 实际发生，1次脚本响应、revision2 |
| 依赖bootstrap | 精确生成SHA拒绝，四个辅助路径差异 |
| 完整build、12原程序323叶、交付、replay | 未观察 |
| 818作者文件 | 原SHA保持 |
| compile容器清理 | 实际removed且独立inspect不存在 |

不能将未观察填通过/失败，不能称“完整模板已合格”或“模型必需”。脚本参考不是实际Agent推理；rtorrent与libtorrent是已见强关联development组，非holdout。本次不新增规划费用收益、自然恢复率、策略排名、P2或RQ3分母。

## 证据与异常保留

运行release `55c637f61d4725a70959147b3bd12deda33056f2`；242冻结组件。manifest/preregistration：`benchmarks/{manifests,preregistrations}/cpp-build-rtorrent-actual-template-gate-v1.*`。

raw：`/home/yiwei/.codex/outputs/forge-rtorrent-actual-template-gate-v1`，inventory `cfbe2d431f815f0a8773c7fcf845544ea1e137474f4e59e1aaaaf8d74fbcb0a3`，1962文件、0链接、29862397bytes。只观察一个槽、未观察槽0；未严格完成1。

原seal因root生成的0600文件无法读取而失败，原日志保留。随后以只读raw/repo挂载独立采集完整清单和seal到会话收据，仅将缺失的两份元数据追加回原raw；没有改原文件/权限/日志/结果字节，没有重跑实验。独立审计使用stdlib在只读挂载核验清单、运行Git组件、父参考完整清单、818文件、五命令、失败日志、初始来源、脚本计量、物理日志清理与未观察各层。独立审计首版误要求只有一次路由事件，忽略第二交接先记录路由后被门禁拒绝；该失败实现/收据保留，修正后valid。宿主独立Docker inspect确认两种容器身份均不存在。

会话 `/home/yiwei/.codex/outputs/forge-rtorrent-template-session-2026-10-21/` 保存run-v1.log、readonly-capture-*、audit_failure.py/v2、independent-failure-audit.json、actual-cleanup-audit.json、检查与最终发布/知识库收据。派生：`benchmarks/analyses/cpp-build-rtorrent-actual-template-gate-v1-results.json`。

27相关回归通过；产品2409passed/44skipped/27warnings，Ruff与606文件格式通过。历史pytest临时目录权限清理告警保留；本轮原raw新权限障碍单独记录，不混同历史warning。没有前端改动。

## 下一步

先在新免费身份验证root-first下的标准生成关系及显式恢复配方，保留作者源码/测试和精确输出验证，启动时明确宿主UID/GID以避免不可读新文件。需独立顺序对照及完整原测试/交付/replay资格，不能只更改SHA裁判来制造成功。通过后再冻结共同材料/装配/恢复/费用口径一致的真实canary和比较；未来付费仍需新具体身份和有效预算/时窗。无需改变论文主线。

本轮免费窗口UTC09:50:30–11:50:30不延长，原paid不续用；本身份已经停止，禁止续跑/补槽。旧别名校准仅是原顺序生成形式资格，不推广到所有生成顺序；旧资格与失败不改。最终HEAD三CI全成功后仅合科研依赖分支，不进main，发布事实以GitHub和final-publication-audit.json为准。用户HTML原SHA保持未跟踪。
