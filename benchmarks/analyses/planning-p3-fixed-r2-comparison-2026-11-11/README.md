# P0/P3固定R2比较：完整36槽（待用户审核）

身份`cpp-build-planning-p3-fixed-r2-comparison-flash-v1`。18项目、每方法每项目一次，36/36终态；P0/P3独立规划、相同R2恢复，不共享初始方案。

- [报告](../../../docs/research/2026-11-11-planning-p3-fixed-r2-comparison-results.md)：固定分母结果、阶段费用、具体失败和共同限制。
- [summary.json](summary.json)：冻结入口自动输出的全分母与阶段统计。
- [slots.csv](slots.csv)：36槽，保留未观察null、主构建/交付、全部费用、初始/恢复分项与原因。
- [derived.json](derived.json)：18配对、三系统分层、全量复算；[derive.py](derive.py)为相同派生入口，在对应工作区以python执行，原件只读、输出至独立会话。
- [usage-verification.json](usage-verification.json)：335响应/4037418Token/1.337265美元，均deepseek-flash，未知0。
- [cleanup.json](cleanup.json)：36cleanup、57容器114引用实查不存在。
- [seal-completion-receipt.json](seal-completion-receipt.json)、[seal-audit.json](seal-audit.json)：自动清单权限失败后以相同实现只读读取补全首次seal；未改原件、无重跑。

主构建P0/P3为17/18、15/18，交付11/18、10/18；模型费0.3982293/0.9390357美元，累计1980.60/1572.14秒。P3高费、较少完成；较短总时不能当等完成加速。5项目局部低费保留。结果先审，不自动写论文，不替换P0。

原件`/home/yiwei/.codex/outputs/forge-planning-p3-fixed-r2-comparison-flash-v1`；inventory`479ce9ab398dd45371d03f2d0bff0adeb37228dafd6668a54aa7afe590a93ca9`。派生会话`forge-planning-p3-comparison-session-20261111`保存日志、授权及launch-note；一次错误session名称引用被授权门禁在正式目录创建/凭据读取前拒绝，0Provider。旧提案session行政runner.log被重定向覆盖，旧提案正式raw不变；与本批36正式槽分开，未重试正式槽。

P3提案费0.317073、R2提案费0.139614美元为历史单列投入。不混入E55恢复比较、旧H1/H2分母，不声明18项目最终未见泛化或显著性。共同轻量参考、交付名称/权限问题影响绝对交付率，全部保留。
