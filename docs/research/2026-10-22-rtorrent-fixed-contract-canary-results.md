# rtorrent 固定合同共同引用真实 canary v4 结果

独立`cpp-build-rtorrent-common-canary-v4`三策略固定各一次，0 strict/3观察/0未观察槽；55真实请求、1013142Token、保守估费1.59653472美元、未知用量0。整批固定顺序正常结束（原stop_reason=null），三槽分别触达工具预算；全部费用与失败保留，无自动重试/补槽。

| 策略 | strict | 请求 | Token | 美元 | 停止 |
|---|---|---:|---:|---:|---|
|tool_plan_workflow|False|17|304342|0.43602504|AgentWorkflowBudgetExceeded|
|model_plan_workflow|False|17|333030|0.57004728|AgentWorkflowBudgetExceeded|
|strong_tool_agent|False|21|375770|0.5904624|AgentWorkflowBudgetExceeded|

## 分层观察与完整成本

- `tool_plan_workflow`：build观察=False，原测试观察0/12、完整0/12/0叶；精确交付验证=False，replay观察=False。源码读39次/不同参数11种/重复28次，固定合同读1次；初始规划模型费=0（强工具不独立拆规划），各阶段全费用见派生JSON。
- `model_plan_workflow`：build观察=False，原测试观察0/12、完整0/12/0叶；精确交付验证=False，replay观察=False。源码读37次/不同参数12种/重复25次，固定合同读6次；初始规划模型费=0.57004728（强工具不独立拆规划），各阶段全费用见派生JSON。
- `strong_tool_agent`：build观察=False，原测试观察0/12、完整0/12/0叶；精确交付验证=False，replay观察=False。源码读16次/不同参数8种/重复8次，固定合同读12次；初始规划模型费=None（强工具不独立拆规划），各阶段全费用见派生JSON。

所有初始/读取/输出/失败/纠错/恢复请求均计量。没有执行到的测试、交付、replay保持未观察，不能填该功能本身通过/失败。strict必须满足原818作者文件、40生成SHA、12原程序323叶、双普通ELF/CLI/精确交付/同镜像空目录重放及实际cleanup；引用不替换执行器原完整脚本。单一已见development的rtorrent+rakshasa-libtorrent族、每策略一次，不作总体/排名/显著性/holdout或规划净收益。不同工程版本不作因果处理效果；接受局部优势和取舍，失败不等于硕士论文主线无效。

## 证据与核验

- release `456737d9960d3810ac9fe819cab861d976abbdad`；候选8352b0a68437c93036fd1ce1a32410b35ae8b57820d65adcb2e3810a5232cbe2；279组件。
- raw `/home/yiwei/.codex/outputs/forge-rtorrent-common-canary-v4`；inventory `3c95b530dedda691bc1d7d665b176cc08abd522e5fa46307f72eaa277bd56674`；5624文件/0链接/99579993字节。
- 独立stdlib清单/Git父链/实际请求和原脚本完整还原/工具schema与由冻结来源重建的系统提示/原响应逐Token费用生命周期/两个旧阶段完整费用/源码和验收层审计valid；实际容器资源及不存在审计valid。强工具原system的共同合同说明位于AUTOMATIC与CONTEXT之间，资格fixture位于原system末尾；审计按冻结源码精确重建该拼接位置，原文字与同一合同说明逐字保持。
- 52相关回归、产品2521 passed/44 skipped/27 warnings及Ruff/617格式、实际CLI与原授权及两个旧账本免费核验通过。最终结果HEAD三CI后仅合科研依赖分支，发布以GitHub及final-v4-publication-audit.json为准。
- 原用户10美元/UTC2026-10-21T15:30:52–19:30:52（准备计入）/请求不限/无自动重试，原3900秒新槽/请求预留不降。累计名义3.27044256美元，原账本累计3.27044256000000009美元、余额6.72955743999999991，原浮点尾数保留，不续期。
- 派生benchmarks/analyses/cpp-build-rtorrent-common-canary-v4-results.json；会话forge-rtorrent-real-session-2026-10-21保留运行/独立审计/费用/工程检查及发布收据，RQ3/P2/主线/用户HTML保持。

## 事后上下文保留诊断

只读解码所有实际请求后，观察到当前共同middleware仅发送一个Human权威状态包，旧助手回答、工具调用配对及reasoning_content不以原生会话形式传回。源码工作集受24k以及总消息49k淘汰规则控制。完整raw仍保留原响应和工具反馈，最近三个工具反馈也可能保留部分文本，不能将工作集缺失等同于模型毫无相关信息。

- slot-1：17请求均为单Human包的数量=17；空源码工作集5次。提出read_source 40次，其中目标相同区间仍在解码工作集0次；规范化参数曾建议过的重复32次。这里是模型建议数，预算可能阻止尾部工具实际执行，不能混作实际工具计数。
- slot-2：17请求均为单Human包的数量=17；空源码工作集0次。提出read_source 37次，其中目标相同区间仍在解码工作集0次；规范化参数曾建议过的重复27次。这里是模型建议数，预算可能阻止尾部工具实际执行，不能混作实际工具计数。
- slot-3：21请求均为单Human包的数量=21；空源码工作集0次。提出read_source 16次，其中目标相同区间仍在解码工作集0次；规范化参数曾建议过的重复8次。这里是模型建议数，预算可能阻止尾部工具实际执行，不能混作实际工具计数。

这支持优先核验共同Harness的会话连续性与证据保留，不支持把重复读取直接解释为模型无效探索，也不证明保留会话必然提升成功率。下一步应先做零Provider接口资格，再决定独立真实身份；不继续靠追加表示压缩版本追求好结果，不修改原验收、RQ3分母或论文主线。
