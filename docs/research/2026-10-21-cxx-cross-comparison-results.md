# C++ Make/Autotools三策略比较结果

跟踪#568。独立身份`cpp-build-cxx-cross-system-comparison-v1`完整18观察、9 strict、0未观察；tinyxml2九槽全部严格完成，libconfig九槽全部在bootstrap后因原文件被改写而拒绝，后续build/完整作者测试/交付/replay未观察。不能将它们称为九个功能测试失败或项目无法编译。

## 共同资格与公平性

`cpp-build-cxx-cross-system-common-gate-v1`六槽6/6 strict，0真实Provider、5脚本响应、0Token及模型费；tinyxml2原/replay508断言，libconfig原/replay8PASS+1上游XFAIL、16/16 tinytest，原文件SHA/索引/no HEAD、完整精确静态交付及实际cleanup独立通过。inventory `81b830d1892963bd978f342ca7ecdcc5a0abf68f70adb187dae517ca902dcf99`，7897文件/12链接/212278853bytes，运行release `409cd41b676e3914c64f721dcabfb9ac3c2c4edd`。主审计v2将脚本响应与Provider调用分开标记，首版字段命名错误收据保留，不改raw。

有效来源是tinyxml2原reference-v1合格槽与libconfig独立header-v1合格槽；原参考仍1/2，不拼成原身份2/2。完整来源/参考证据见[参考资格报告](2026-10-21-cxx-cross-reference-results.md)。人工参考只供Fake资格，未进入真实Agent。

每项目三重复，每方法在三个执行位置各一次，两项目合计六种排列；在新Provider结果前冻结角色和项目族暴露。task显式build_system对所有方法相同，仅工具候选新增唯一普通根Make入口；Autotools缺可靠候选继续拒答升级，不猜依赖/参数、不删除此项目。两个Workflow共用初始/恢复Agent、只读工具、材料meter、方案装配、固定测试/暂存、状态和预算；强工具Agent是整策略参照，其工具权限及控制循环不同，不能把三者视为仅有一个规划变量的消融。

192组件，candidate SHA `b699ea25c2ea071df06b91153f020ff02604edf3de17932f5fed1df33088cf7c`；运行release `0eb4d96dffa899f33d32acde9db87625334714ee`。UTC20:42:45唯一启动，20:54:36封存；沿本轮20美元共享预算/原UTC22:07:35截止，stage最多预留9美元，3900秒新槽准入、外层21:52:35清理预留不变。无自动重试/补槽；所有初始读取/生成/输出/失败及恢复成本均计入，失败未替换。

## 全部冻结槽位

| 策略 | strict/6 | 请求 | Token | 保守估费USD | 全流程累计臂秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 工具规划Workflow | 3 | 10 | 131865 | 0.24117060 | 239.939251 |
| 模型规划Workflow | 3 | 18 | 204422 | 0.36655608 | 327.523775 |
| 强工具Agent | 3 | 22 | 192287 | 0.27362940 | 134.068338 |

全部臂时间包括初始化、来源准备、读取/输出/纠错、原执行、验证及cleanup；失败也计入。费用为冻结输入/输出单价1.32/3.96美元每百万Token的保守估算，不是账单实扣。libconfig未完成交付，因此不能根据其较短停止时间宣称构建更快。

## 分项目结果

| 项目/策略 | strict/3 | 请求 | 保守估费USD | 全流程累计臂秒 |
| --- | ---: | ---: | ---: | ---: |
| tinyxml2/工具规划Workflow | 3 | 0 | 0.00 | 32.608930 |
| tinyxml2/模型规划Workflow | 3 | 6 | 0.09291480 | 112.364070 |
| tinyxml2/强工具Agent | 3 | 11 | 0.10347216 | 59.384189 |
| libconfig/工具规划Workflow | 0 | 10 | 0.24117060 | 207.330321 |
| libconfig/模型规划Workflow | 0 | 12 | 0.27364128 | 215.159705 |
| libconfig/强工具Agent | 0 | 11 | 0.17015724 | 74.684149 |

tinyxml2三次工具规划均0模型请求、0Token、0模型费严格完成。这支持此固定默认Make任务上的局部节省；不能据此估默认模板的自然覆盖率或推广到其他项目。模型规划6请求/0.09291480美元，强工具11请求/0.10347216美元；模型规划虽然请求少，累计臂秒112.36高于强工具59.38，不能声称方案方法全面更快。

libconfig工具模板三次均拒答，其与模型Workflow的三个首次Agent输入，仅归一化实际递减node_seconds后逐字段相等。两者后续请求/费用差不能归因为“工具省去了初始规划”；这三对实际都调用相同初始Agent。强工具总请求22比模型Workflow18多，但总估费0.27362940低于0.36655608，说明请求数不能代替Token与费用。

## 源码拒绝与分层解释

libconfig九槽均执行`autoreconf -fi`或`autoreconf -fvi`，每槽都改写同一18个原仓库文件：ac_config.h.in、INSTALL、11项aux-build辅助文件及5项m4宏（实际完整列表以独立拒绝审计为准）。原header明确含“Generated from configure.ac by autoheader”，其余含生成/工具模板及辅助脚本；这些事实不自动赋予写入权限。源码合同在首个bootstrap执行后即停止，九槽后续build、作者完整测试、暂存与replay均未观察；不把未观察填失败或成功。

原固定完整源码不改的任务边界对三策略一致，没有为了好结果改裁判、恢复原文件或豁免生成文件。独立人工参考表明存在保留原文件的可执行路径，但不能将该参考注入真实Agent、据此回填九槽或声称它们本来会通过。是否让未来任务明确允许已声明的构建生成文件更新，属于任务定义/主张边界决定，须用户另决；旧证据永久不变。

| 层 | 通过 | 失败 | 未观察 |
| --- | ---: | ---: | ---: |
| 原文件SHA保持 | 9 | 9 | 0 |
| build实际执行 | 9 | 0 | 9 |
| 固定完整作者测试 | 9 | 0 | 9 |
| 精确交付及clean replay | 9 | 0 | 9 |
| 实际容器cleanup | 18 | 0 | 0 |

这张表是本批固定18槽的分层描述，不拼入RQ3旧14/43，也不当自然误接受率。9次终止均没有进入测试，不能证明验证发现九个功能缺陷。本批没有Workflow失败交接或plan.revised，不能新增RQ2恢复效果或最小增量收益主张；没有新的同源合理策略动作分歧，不加P2。

## 支持的判断与下一步

保留主线：工具规划对默认兼容任务存在可复现的零模型局部收益；复杂任务上仍需Agent。已有六槽模板消融又表明，省去初始规划可能被更高恢复费用抵消，不能把“工具规划”当无条件优势。两个工作包仍是领域化方案/状态接管方法，以及固定候选的分层验证与实证研究，不宣称新通用规划机制或两个独立创新点已经成立。

下一步先将任务要求区分为作者源文件、供应的生成模板、构建过程中新增生成物，审阅保持全部原文件SHA的适用范围；在用户确认未来合同前不放宽。与此同时可做零Provider、无构建的前瞻来源目录，为后续更大独立项目队列准备，不能按当前结果挑优势项目。当前两项目及参考均已见开发样本，tinyxml2历史CMake同族已暴露、libconfig为C/C++混合，不作holdout、总体/大型C++/自然失败或模型排名推断。

## 证据与发布

50真实请求/528574Token/估费0.88135608美元、未知0。与本轮原18槽1.45084632及六槽0.73349496共3.06569736美元，三paid stage全部completed；共享预算20美元非支出目标，不为花完预算追加请求。不同身份不合并估效果。

raw `/home/yiwei/.codex/outputs/forge-cxx-cross-system-comparison-v1`；inventory `7f93db80f09e2f46a78cac64df12d6df6b48fb7bbc99ce464ea76fb4de1b0745`（15860文件/0链接/316652838bytes）。会话`/home/yiwei/.codex/outputs/forge-cxx-continuous-session-2026-10-21/`保存cross-paid-independent-audit.json、cross-paid-details.json、cross-paid-shared-text-audit.json、cross-paid-initial-inputs.json、cross-paid-source-rejections.json、cross-paid-derived-metrics.json及各独立实现、授权/启动/终态/共享账本。全部独立审计valid；50实际请求中的22个可逆引用包完整SHA/任务/方案解码匹配，50k/8k门禁保持。九个strict的原/replay508断言、源码索引/no HEAD、精确静态交付及18槽实际cleanup均通过。

新12回归、产品2282 passed/44 skipped/27 warnings、Ruff通过。直接将历史冻结测试混入当前runtime的13导入错误保留日志，按既有Makefile/三套CI分隔验证，不修旧身份。最终结果HEAD三CI后仅合科研依赖分支，发布以GitHub与最终收据为准，不进main；用户HTML不动。
