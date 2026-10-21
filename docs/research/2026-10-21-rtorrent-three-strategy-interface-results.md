# rtorrent 三策略共同接口资格结果

#583：基础设施/工程资格，组合接口覆盖：通过。0 Provider、0真实Token、0模型费用。三种正常路径和两条恢复来自不同独立身份，不能称单身份五槽全部成功，也不估计模型策略成功率。

| 独立身份 | 场景/策略 | strict | 脚本响应 | 原命令数 | 原/replay完整测试叶 |
| --- | --- | --- | ---: | ---: | --- |
| cpp-build-rtorrent-three-strategy-gate-v1 | normal/tool_plan_workflow | 未通过 | 0 | 1 | 0 |
| cpp-build-rtorrent-three-strategy-gate-v1 | 未观察4槽 | 未观察 | — | — | 未观察 |
| cpp-build-rtorrent-three-strategy-gate-v2 | normal/tool_plan_workflow | 通过 | 1 | 11 | 323 / 323 |
| cpp-build-rtorrent-three-strategy-gate-v2 | normal/model_plan_workflow | 通过 | 1 | 11 | 323 / 323 |
| cpp-build-rtorrent-three-strategy-gate-v2 | normal/strong_tool_agent | 通过 | 1 | 11 | 323 / 323 |
| cpp-build-rtorrent-three-strategy-gate-v2 | controlled_recovery/tool_plan_workflow | 未通过 | 1 | 8 | 0 |
| cpp-build-rtorrent-three-strategy-gate-v2 | 未观察1槽 | 未观察 | — | — | 未观察 |
| cpp-build-rtorrent-recovery-interface-gate-v1 | controlled_recovery/tool_plan_workflow | 通过 | 2 | 12 | 323 / 323 |
| cpp-build-rtorrent-recovery-interface-gate-v1 | controlled_recovery/model_plan_workflow | 通过 | 2 | 12 | 323 / 323 |

## 新证据与完整任务

两规划来源通过同一StagedVerificationTask装配构建动作→系统精确暂存→完整固定作者测试→独立CLI；强工具使用同一边界、固定测试、可信提交及权威配方选择。完整测试保留verify配方，产物短smoke仅绑定CLI。每个strict槽原及同镜像空目录replay均完整12原程序323叶（主三102＋源码依赖九221）、818原文件、40精确生成SHA、原功能/断言、源码索引/no HEAD、双普通ELF精确集合/类型/大小/SHA/CLI与实际cleanup。系统254包使用不可变二进制镜像，不宣称全部源码重建或跨主机复现。

两恢复槽真实执行build=false后取得权威handoff，返回正确脚本动作、revision2；共同准备及前六动作共七成功前缀的原command_id保留，仅build后缀重跑。完整replay仍重建全部源码依赖，不跳过前缀，不包含false。脚本修订只证明恢复接线，不证明自然恢复率或成本收益。false在主构建前退出，本次没有验证已有坏中间产物的物理清理，不改变旧libverto恢复失败。

## 保留失败与材料修复

v1在共同Git索引准备时因未声明.git新输出拒绝，1失败/4未观察，0脚本响应。v2只追加系统.git输出目录：三正常路径strict；第四恢复真实false失败后材料超过50,000字节，在第二次脚本响应之前停止，0恢复响应/修订，第五未观察。两个旧身份均封存，源码保护、实际cleanup及独立audit通过；新恢复身份不回填旧结果。

事后只读重建原第四槽恢复材料，用于定位表示问题，不冒称原请求实际发送。新恢复表示在相同长字符串引用基础上，以可读原文子串字典去重；不删/截任务、测试、命令、状态或失败，不提高50k消息/8k schema门禁。既有投影后完整原包SHA及独立逐字还原验证，正常初始表示不变；此前日志预览界限不变，完整原日志仍可按授权路径显式重读；实际两个恢复请求的字节与SHA见independent-recovery-materials-audit.json。该表示资格没有验证真实模型的理解或费用收益，真实比较前仍需独立canary。

## 工具规划与公平性

现有模板产生autoreconf -fi，原任务仅声明-ivf，初始拒答升级是精确命令形式差异，不能说模型在此必需或工具不能处理源码依赖。两Workflow实际正常初始请求仅归一化remaining_budget.node_seconds后逐字段相同（45889/45890消息字节、schema2725）；本任务没有观察到工具省掉初始模型规划。未来随机轨迹差不能归因此。人工参考只用于脚本门禁，未来真实Agent不得读取参考、开发记录或个人知识库。

独立bootstrap-alias资格：通过。已观察2个case，合格2个；fi/ivf各自空源码仅运行标准生成，合格要求818原文件不变、40输出精确SHA一致、实际cleanup通过。这里只验证固定版本/镜像下生成内容，build、作者测试、交付、replay均未观察；不回填旧拒答，不称完整模板已合格。未来接纳fi须新身份预声明并实际资格验证。

## 证据、工程验证与下一步

rtorrent/libtorrent为一个已见强关联development项目族，非holdout。两CPU、network none、节点/原及replay1200秒、准入2700秒、cleanup120秒，UTC07:30:59.253248–10:30:59.253248免费窗保持。任一失败停止，其余未观察；0凭据/Provider/费用，不沿用旧付费授权。

- `cpp-build-rtorrent-three-strategy-gate-v1`：release `2064849ffb7e8d267a3cce76dab5137396011106`；inventory `3dee8c8eff808a82f2186565ba2ffa17399844e302839c32d34524d70c456a38`；raw `/home/yiwei/.codex/outputs/forge-rtorrent-three-strategy-gate-v1`。

- `cpp-build-rtorrent-three-strategy-gate-v2`：release `fa79b0df2663287436cd99e4826f9ac3177ea889`；inventory `1bdb253e5c58eb246231310e368d667ea7202073c75e11e8d708589da9a15717`；raw `/home/yiwei/.codex/outputs/forge-rtorrent-three-strategy-gate-v2`。

- `cpp-build-rtorrent-recovery-interface-gate-v1`：release `94253c061dd4063c3c25d42b50bb03048882eafb`；inventory `46bd8ba50bf36e6d75b392f9d1b1dc561890afcd921fb04bb472b68a6fa580eb`；raw `/home/yiwei/.codex/outputs/forge-rtorrent-recovery-interface-gate-v1`。

- 标准生成形式资格：release `dbe6d67a868e8034f8eccac2d46ceb134873bd0e`；inventory `954be4d2443d802c9fee1e452d49b26929b0bea3f8c2483a04b53b7d4cb19fcd`；raw `/home/yiwei/.codex/outputs/forge-rtorrent-bootstrap-alias-qualification-v1`。

协议位于benchmarks/manifests各同名JSON及preregistrations同名MD；暴露登记为benchmarks/analyses/cpp-build-rtorrent-role-exposure-v1.json。会话目录 /home/yiwei/.codex/outputs/forge-rtorrent-interface-session-2026-10-21 保存独立标准库清单/Git组件/父链/原及replay全部叶/生成/索引/双ELF/CLI/恢复前缀与实际容器审计、逐字材料审计、检查及发布/知识库CAS收据。

工程检查：25相关测试通过；产品2405 passed/44 skipped/27 warnings，Ruff/格式通过。历史pytest临时目录权限清理告警保留，无前端改动；这些不是科研效果。一次独立审计误将多行python3 -c按单行解析，失败收据live-slot-1-recovery-audit-failure.json保留；改为按Replay step完整解析后只读核验通过，未改raw或运行器。

下一步先前瞻接纳经资格的合理生成形式，再验证实际通用模板的路由/失败升级，避免把偶然形式差异当模型必要性。之后冻结共享相同材料/工具/测试/恢复/全部费用口径的真实canary或比较；初始/读取/输出/拒答/纠错/恢复均计入。强工具改变执行控制，不能把三策略差异全部归为规划来源。旧libconfig九槽、RQ3原固定分母、P2和硕士主线不变。未来付费需新具体身份与有效预算/时窗；最终HEAD三CI后仅合科研依赖分支，发布事实以GitHub及final-publication-audit为准。
