# Jev 自然失败 Linux applicability v4 预注册

日期：2026-10-12。追踪：Issue #415。候选 identity：
`cpp-jev-natural-failure-linux-applicability-v4`。

## 研究问题

修正后的 source-only 门禁能否避免 v3 将局部 Apple/Windows 文本误判为项目级平台限制，同时排除裸机、
firmware、kernel、ROM 和真正的平台排他入口，并在排除 v1-v3 全部已观察项目后，为 CMake、Make、
Autotools 各形成至少 12 个唯一 reserve？

## 冻结方法

- 入口扫描先去除 CMake/Make/Autoconf 注释；
- endpoint signal 与 host-platform signal 分开记录；
- `non_host_endpoint` 优先排除，不能被 Linux 宿主文档覆盖；
- 明确 Linux 入口或文档路径优先于局部 Apple/Windows host-platform signal；
- 文档排他声明必须以项目、应用、工具或库为主语；
- 无法读取入口或存在无法消解的证据缺口时为 `ambiguous`，fail closed。

协议校验固定运行 14 个 regression case，包括 v3 的 7 个真实排除边。真实回归的期望为 5 个
`linux_applicable`、2 个 `platform_ineligible`；不能在正式结果后改标签。

## 样本与预算

- GitHub C/C++ repository search 各最多 400 项，总计最多 800 项；
- 排除冻结 v2 catalog 和 v3 formal report 中的全部项目族；
- 固定默认分支 HEAD 的 exact commit，只读根 tree、根入口和最多 6 个根级构建文档；
- 总墙钟上限 7200 秒，单个 GitHub API 请求 60 秒；
- 0 build、0 Docker、0 credential、0 Provider、0 model token。

## 通过与停止

通过必须同时满足：

- regression fixture 14/14；
- CMake、Make、Autotools 最大唯一分配均为 12；
- infrastructure failure 为 0；
- marker、report 和 evidence inventory 审计通过。

通过决定为 `proceed_to_natural_failure_build_reference_qualification_v4`；否则为
`stop_natural_failure_linux_applicability_v4`。唯一 attempt 一旦创建，无论完成、失败或部分完成均永久只读，
禁止重跑、replacement、backfill、调规则或改标签。

## 解释边界

通过只证明 source-only 静态必要条件和 reserve 数量，不证明 Linux 构建成功、自然失败或 reference closure；
失败也不评价 Jev、Agent、动作路由、成本收益或动态预算控制。后续 build/reference qualification 必须使用
新的 spec、identity、预算和 evidence 根。
