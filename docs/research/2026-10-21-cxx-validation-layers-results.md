# 已见C++真实比较队列的分层验证复核

Issue #567，结果分析、0Provider/模型费，不重跑构建、不改变原裁判。独立标准库实现`forge_audit_cxx_fixed_layers.py`按`cpp-build-cxx-fixed-cohort-validation-audit-v1.json`逐槽消费两个封存队列；18和6分别固定，不混入既有RQ3的14/43行，也不合并计算效果。

## 各层实际观察

数字为通过/失败/未观察，均以该队列全部槽为分母，并非自动串行漏斗。构建取最新build退出码与超时；固定任务检查取最新精确smoke命令；作者测试要求完整JUnit testcase数和实际执行通过；暂存与replay分别取真实记录，无记录就是未观察。源码逐原文件SHA核验，cleanup按原/replay容器名和ID实际查询不存在。

| 固定队列 | 槽数 | 最新build | 固定任务检查 | 作者完整CTest | 暂存 | clean replay | 原文件/cleanup | strict |
| --- | ---: | --- | --- | --- | --- | --- | --- | ---: |
| cxx-comparison-v1 | 18 | 18/0/0 | 15/3/0 | 15/0/3 | 15/0/3 | 15/0/3 | 各18/0/0 | 15 |
| task-selected-comparison-v1 | 6 | 6/0/0 | 6/0/0 | 6/0/0 | 6/0/0 | 6/0/0 | 各6/0/0 | 6 |

18槽的3个差异都发生在snappy Workflow：构建通过，但固定功能检查发现依赖功能不满足；随后恢复材料达到原50k门禁，作者完整CTest/交付/重放未观察。不称发现3个功能bug，不填后续测试失败，不据3/18估计自然误接受率。其余15槽和新6槽均有原/replay作者完整测试、配置功能、源码索引/no HEAD、精确交付与实际cleanup的第二独立详情审计。

新6槽最终各层通过，不能据此声称验证层提高方法成功率或某层已无必要；其中3次真实检查失败后修订，仅保留共同源码准备、清空build并完整重走后缀。主表是终态分层，不能掩盖过程中的失败。两批共同材料接口和generator条件不同，不将21/24或跨批15→6作效果估计。

## 能够支持的研究结论

成功build不足以证明任务的必要功能、完整作者测试与可复现交付已经满足。分层事实能定位在配置功能、测试、暂存或replay的具体缺口，并区分失败与尚未观察。该结果支持自动化编译领域验证方法和系统评测的实用价值，尚不等于独立新通用验证算法或已成立第二创新点。

旁证#565 libconfig原参考虽完成8PASS+1XFAIL/16tinytest和工程replay，仍因autoheader重生成原模板不合格。它是强原文件合同的适用域限制，不是已证实功能错误；新独立身份通过延续AUTOHEADER=true保持原模板而闭合，没有降低标准或回填原失败。此例不加入上述18/6分母。

## 可复核证据

- 原18 inventory：cdfe5ca87f1eae4b90fac2fb73f0ac0339b85414082b3b63ce1ad4d8c366520f；raw forge-cxx-comparison-v1。
- 新6 inventory：0aa0d9dddbfad8cf4a4d1b35fd9da4b73793eb00cc67774bd9c8174234d7d728；raw forge-task-selected-comparison-v1。
- 会话forge-cxx-continuous-session-2026-10-21/rq3-both-cohorts-audit.json为首版独立结果；版本化实现另写新收据并逐字段比对，不覆盖它。实现与冻结规则SHA随结果保存，原raw完全只读。
- 两批原始主费用/源码审计与完整测试第二审计分别见`independent-real-audit.json`/`cpp-details-independent-audit.json`和`selected-paid-independent-audit.json`/`selected-paid-cpp-details.json`。

```bash
python3 scripts/forge_audit_cxx_fixed_layers.py benchmarks/analyses/cpp-build-cxx-fixed-cohort-validation-audit-v1.json /新的独立审计结果.json
```

脚本仅对已有具名容器进行只读inspect。复核需原始冻结证据可达及Docker运行时，不读取Provider凭据、不写旧证据。下一步继续跨系统参考和三策略共同接口资格，旧RQ3分母、主线与验收不变，不加P2。

版本化结果 `benchmarks/analyses/cpp-build-cxx-fixed-cohort-validation-audit-v1-results.json`；最终实现SHA 5466b5644190a28d5a5fea21fdfc5cd8a3f168fd29de687be56c7a42133ef733，冻结规则SHA 9fd0d2ee716bcbd3ac461308ab3f57053b71635ada0b479b6800355140da49e9。首版与最终版全部24行/层计数逐字段相等，收据rq3-versioned-equality-receipt.json；反篡改、漏行分母与身份拒绝4测试及实际24行重算通过。
