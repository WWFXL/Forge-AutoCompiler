# 三系统受控构建方案恢复资格结果

Issue #506 / PR #509，身份`cpp-build-plan-recovery-qualification-v1`，正式运行release1e2a0037。这是已见开发项目受控资格，不是自然失败率或算法效果实验。固定miniz(CMake)、pigz(Make)、libite(Autotools)，初始人工合格方案分别注入不存在target、不存在CC和跳过bootstrap，模型只接收坏方案、实际失败日志及只读源码，不获得正确人工参考。

## 门禁与真实结果

同协议九槽零Provider门禁9/9预期成立：三正常strict、三静态在首次失败交接后停止、三脚本模型修订后strict。完整测试、固定source/image、源码不变、精确交付、clean replay和cleanup均保持。门禁raw `/home/yiwei/.codex/outputs/forge-plan-recovery-gate-v1/`，3145普通文件/27链接/80223279 bytes，inventory `cc4fd0eaf41915ec4b5145c062e4b49b9fa641738089e0cadcf93e926d1d985d`；独立audit valid=true、issues=[]。

| 项目 | 原错误与退出码 | handoff/修订 | 保留前缀 | 请求 | Token | 估算美元 | Shell |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| miniz | 错误target，2 | 1/revision2 | configure | 2 | 24820 | 0.03635808 | 5 |
| pigz | 错误CC，2 | 1/revision2 | 空 | 2 | 14940 | 0.02284920 | 4 |
| libite | ./configure缺失，127 | 1/revision2 | 空 | 2 | 21534 | 0.03514104 | 7 |

三条真实恢复全部strict completed，合计6请求/61294 Token/$0.09434832/16条Shell。失败动作真实执行后才交接，各一次有效修订；初始失败命令和被失效旧步骤未进入最终replay配方。固定完整测试字段和任务身份在修订前后保持。0未知用量、0自动重试、全部cleanup成功，未补跑或替换任何槽位。

独立审计还检查首变化前缀、completed后缀失效、plan身份/固定测试不变、最终recipe不消费失败或已失效旧命令。它支持这三类受控失效的恢复/失效规则闭合；不证明自然项目恢复率，也不能以该静态停止控制替代合理自动纠错规则基线。

## 封存、验证与解释

真实raw `/home/yiwei/.codex/outputs/forge-plan-recovery-real-v1/`，1423普通文件/40链接/36733860 bytes，inventory `a47d84aa86bde07f5dda19f492bf3c7be3834f7b52c1e6c433d32ddda24a9f67`。独立stdlib audit `/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/recovery-real-v1-audit.json` 为valid=true、issues=[]，核验源码/归档/组件/计量/固定测试/replay/cleanup和状态转移。门禁独立审计为同目录recovery-gate-v1-audit.json。

8项针对性测试、Ruff/format及完整父封存只读validate通过。首次validate发现来源父证据采用旧封存格式，正式证据创建前改用原audit_frozen并补篡改检测测试，未改变旧证据；最终结果head须三项实际CI均SUCCESS后才合并。

初始方案由人工给出，不能把这里的恢复费用加入RQ1完整规划策略比较或宣称总体节省。这不是新holdout、不是状态选择器相对强规则的增量，也不支持P2或自然误接受率。阶段$3预留按$0.09434832结算，本轮已知保守估算累计$5.80615200，另旧live未知费用预留$1，预算占用$6.80615200，估算不是账单。

下一步串行#508两项零费用参考修复与#511接管材料工程资格；不追加本固定样本拯救效果。未来RQ2需同源状态下候选方法与合理规则实际动作分歧，并预先固定比较与验收。
