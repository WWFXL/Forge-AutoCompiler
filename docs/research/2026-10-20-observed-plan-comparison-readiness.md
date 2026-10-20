# 新观察接口三策略比较的准入准备（#548）

本轮是基础设施阶段，解除“真实比较仍使用旧规划接口”的阻塞。没有新增真实模型效果结果，也没有读取Provider凭据。主线仍为“面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究”；不要求所有指标全面领先。

## 已完成的资格与验证

新独立入口 `scripts/forge_build_observed_plan_comparison.py` 显式接入 `observed_planner`，两Workflow共享ObservedBuildActions、固定完整测试/精确暂存、恢复与费用计量；强工具保留固定测试、批量工具及无参数权威配方submit。真实入口拒绝人工reference，不改产品默认入口或旧冻结执行器。

新身份 `cpp-build-observed-plan-dispatch-gate-v1`，运行release `daf67a8d`，119冻结组件。开发buffer三策略均strict完成，0未观察：工具初始0脚本响应、模型1次ObservedBuildActions脚本、强工具1次批量脚本，合计2脚本响应、9条执行命令。全部真实Provider/Token/费用/未知均0。每槽完整Make自测、原源码、精确交付、同镜像空环境clean replay、实际原/重放容器不存在均由独立stdlib审计核验；两个Workflow固定测试/暂存尾部相同。

门禁raw：`/home/yiwei/.codex/outputs/forge-observed-plan-dispatch-gate-v1/`；inventory `e178ed43c64313bbadef9f9c660b02238bd9612bd4f4097c5648399429ccb88a`，253普通文件、0链接、2794095 bytes。独立审计 `scripts/forge_audit_observed_plan_dispatch.py`，收据位于本轮会话目录 `dispatch-independent-audit.json`（valid=true）。三臂墙钟9.277/9.155/9.368秒，只描述脚本门禁，不能当真实模型时间收益。

原#546十四槽资格及17正向路径原/重放检查保持，不重跑、不拼接或改写旧结果。候选同时绑定它们的inventory、独立审计SHA及新调度门禁；已有114组件逐项hash保持，原107组件亦保持。

新增15针对性回归，与相邻比较/观察接口合计49passed；产品2131passed/44skipped/27warnings，Ruff及556文件格式检查通过。首轮测试曾误把全局os.environ替为None，导致pytest后续连带报错；已修为仅替本模块命名空间，重新验证通过，无Provider调用。pytest清理历史临时树时有权限警告，未清理其他任务目录。这些工程检查不替代科学效果。

## 可审阅的真实比较候选

`benchmarks/manifests/cpp-build-observed-plan-comparison-v1.json`，SHA-256 `8a9310f8c89d657b29d9a1b7f56b967c17ba615a2717d2239fda139293bade2b`，120组件。对应预注册为同名Markdown。真实CLI `--validate-only`须在发布前实际通过，0Provider，不把preflight当效果。

libpng/check/libtommath/libsodium各一次×工具规划Workflow/模型规划Workflow/强工具Agent，固定12槽。定向选择旧接口故障和直接模板正例，已见源码/参考/结果，不是holdout。静态只读检查再次确认libsodium直接候选、前三者保守拒绝后升级；详见会话 `static-coverage.json`，不执行构建，不按此删项目。每策略每顺序位置出现1或2次，不能称完全平衡。

两Workflow对比相同装配/恢复下的来源策略；强工具是整策略参照。报告strict和分层未观察、全部初始/拒绝升级/失败/纠错/恢复的费用、请求、输入输出Token、总臂时间、Shell与无效交接；按阶段账本复算。不只分析成功臂，不把请求少等同省钱，不把跨批变化当接口因果，不估总体成功率/自然恢复率或系统排名。

## 授权与下一项决定

真实12槽全部未观察，候选授权与deadline仍null。建议新费用上限20美元、从用户明确授权起最多4小时，准备计入；无自动重试、不补槽，失败保留。每臂1.50美元/请求0.40美元预留与3900秒时限余量、未知usage/实际cleanup失败/模型身份错误停止均保持。原源码/完整测试/精确交付/replay不放宽，不加P2、不改RQ3。

旧HTTP402账户或服务端原因仍未知，不能声称已恢复或余额不足；不读取凭据、充值、换Provider。若用户授权本新身份及服务可用性核验，第一次实际新请求计入本批，不另开未计量探针；再次HTTP402或未知usage立即封存并停止，不重试。旧费用余额不续用。

本轮仅证明入口准入准备与工程资格，不证明新模型成功率或成本改善。后续依据真实取舍与错误类别继续主线，再补C++效果资格。免费工作按Issue→实现/测试→提交/PR/CI→依赖分支合并→关闭Issue→知识库同步；最终发布事实以GitHub及本轮final-publication-audit.json为准，未进入main。
