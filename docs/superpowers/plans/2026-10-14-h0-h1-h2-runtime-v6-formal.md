# Runtime v6 的 H0/H1/H2 Provider 正式比较实施计划

> Tracking Issue：[#453](https://github.com/WWFXL/Forge-AutoCompiler/issues/453)
> 设计：`docs/superpowers/specs/2026-10-14-h0-h1-h2-runtime-v6-formal-design.md`

## A. 冻结正式合同

- [x] 创建并回读独立 tracking Issue。
- [x] 固定三项目、三臂、两次重复和位置平衡顺序。
- [x] 固定主要 estimand、项目族 bootstrap、非劣界和机制激活边界。
- [x] 固定 Provider、单臂/整批预算、停止规则与 create-once evidence。
- [x] 生成并验证 const manifest/schema、runner 与聚焦测试。
- [x] 提交并推送精确 candidate release。

## B. Q0 零 Provider 门禁

- [x] 核对父资格 manifest、report、inventory 与 source archive 哈希。
- [x] 核对 Runtime v3/v4/v6 binding、组件哈希、Docker image 和零 managed resource。
- [x] 核对 clean pushed branch、预算与尚未读取 credential/调用 Provider。
- [x] create-once 写入 Q0 证据并封口。

## C. 18-arm 正式数据采集

- [ ] Q0 通过后读取 `DEEPSEEK_API_KEY`，按冻结顺序运行 18 arms。
- [ ] 每臂保存 assignment、请求生命周期、usage、session、evaluator、Harness 事件与 cleanup 证据。
- [ ] 每个 arm 后检查整批 request/token/费用上界；部分失败按协议保留并停止 replacement。

## D. 分析、审计与交接

- [ ] 计算 strict success 差值、项目族 bootstrap 下界、三臂资源指标和 Runtime v6 激活指标。
- [x] 完成失败 identity 的 inventory、credential/header 扫描、failure audit 和版本化报告。
- [x] 更新 `RESEARCH_STATUS.md` 与 `.claude/memory/project.md`。
- [ ] 提交、推送、回写 Issue #453 并创建以 #451 分支为 base 的堆叠 PR。

历史 identity/evidence 永久只读；不合并 PR，不实现动态预算或 Jev 控制器。

## E. v1 执行结果

- [x] Q0 四项门禁通过，0 credential read / 0 Provider request。
- [x] Q1 在 8 个完整 arm 后于第 9 个 arm 因宿主磁盘耗尽失败关闭；第 10-18 个 arm 未启动。
- [x] 保留零字节部分文件与全部失败证据，不续跑、不补齐、不进入正式 effect analysis。
- [x] 清理 orphan 容器与 51.24 GB 可再生 Docker build cache，封存 failure audit 和 inventory。
- [x] v1 正式决定为 `formal_execution_invalid_due_to_host_disk_exhaustion`。

