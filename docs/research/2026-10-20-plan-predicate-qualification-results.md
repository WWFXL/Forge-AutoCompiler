# 规划观察接口修复与零Provider资格结果

本轮是工程修复与开发资格，目标是解除真实规划比较中的接口歧义，研究主线不变。Issue #546 / PR #547，仅发布到依赖分支`yiwei/534-rq3-natural-failures`，未进入main；产品默认入口未切换。运行release为`3023a66771d4c5de1da1f6239966a95dfaaf8572`，最终发布以GitHub和本轮发布收据为准。

## 修改与不变量

新`ObservedBuildActions`把日志字面文本、文件存在、目录存在分别表达为`stdout_contains/files_exist/directories_exist`，不猜测旧字段含义。文件/目录检查由确定性Python代码执行，编入显式构建命令并在clean replay重复；类型和工作目录边界检查保持，目录仅删除安全尾斜杠。原命令在严格子Shell运行，原非零退出码保留，`exit/exec`也不能跳过随后检查。

恢复反馈区分命令失败与日志断言缺失；后者不被表述为编译命令失败。日志预览不足时仍要求只读工具读取完整日志。目录诊断路径可以规范化，但不递归采集目录。阶段不自动重排；结构/装配/无执行变化建议最多一次额外纠错，全部请求/读取/失败/输出同预算计量，Provider/未知用量/预算异常不自动重试。只改reason/source/expected不能触发重复执行。

两种初始来源共用装配、固定完整测试、精确暂存、只读恢复与Workflow。强工具Agent仍是整策略参照；本轮未运行新强工具效果槽。原107冻结组件hash均不变，原源码/测试/交付/同镜像空环境重放/cleanup裁判不变；不加P2、不改RQ3固定分母、不注入个人知识库或人工参考到正式Agent。

## 身份与中断保留

v1：`cpp-build-plan-predicate-qualification-v1`，release`38c8a033`。发现人工参考buffer使用cc、工具模板使用make，后续脚本恢复混用参考动作会改变原构建命令，缺文件负例首次建议也并非无变化。主动中断，2strict、1部分中断、11未启动；原aggregate的12未完成含该部分槽。cleanup全部通过、0Provider。原manifest/raw保留，不回填，独立中断审计valid=true。inventory`9e8f9572d26a5ca7a8886e1e0e6f05282a67865189cca66d667cbcbb9d102706`，9433文件/51462670bytes。

v2：`cpp-build-plan-predicate-qualification-v2`，只修本轮新夹具，从每槽实际初始动作构造恢复建议；接口模块与历史107组件不改。原工程绝对截止UTC2026-10-20T14:10:23.810185不延长，0凭据/真实Provider/Token/新增费用。开发项目、人工参考、旧实验结果均已见，不称holdout。两个身份不拼接成单一实验。

## 实际观察

14/14槽全部符合预注册观察：13strict与1准确拒绝，0未观察槽；负例内测试/交付/replay未执行，保持未观察。18次本地脚本模型响应、55条受计量执行命令，0真实Provider/Token/费用/未知用量。额外目录诊断采集与系统内部验收/replay不冒充这55条命令；本轮不估效率收益。

| 开发资格 | 槽数 | 实际观察 |
| --- | ---: | --- |
| 三系统×工具/模型正常路径 | 6 | 6strict；Make完整自测，CMake原/重放均14/14，Autotools原/重放均6/6且0skip/0fail |
| 真实非零命令的脚本恢复 | 2 | 2strict；各一次交接/修订，configure成功前缀保留 |
| 路径被错当日志文本的受控修复 | 2 | 2strict；保留同槽原构建命令，改为实际文件检查，原exit0断言失败仍保留 |
| 旧字段、阶段逆序的有界纠错 | 2 | 2strict；各一次纠错，原非法响应保留、全部请求计量 |
| 无执行变化建议的有界纠错 | 1 | 1strict；拒绝首个无变化建议，后续真实修订保留前缀 |
| 缺文件负例 | 1 | exit86准确拒绝；两次无变化建议仍拒绝，0修订，不执行测试/交付/replay |

五个正向恢复槽各handoff1/revision2；负例handoff1/无修订。独立stdlib主审计valid=true，核验全部源码、固定完整测试、精确交付/哈希、同镜像空环境重放、请求闭合及原/重放容器实际不存在。独立AST/日志路径观察审计valid=true：17个正向文件/目录断言在原与重放中均有实际通过输出且文件类型存在，负例仍缺失。

v2 inventory `986b96ae1e601569aa0fc71ea78b96ed1f38a1d1289a024f7a67906d5bd40aa3`，56924普通文件/30链接/230731928bytes，114冻结组件。

## 旧失败的只读开发回归

消费原日志/命令/方案并记录哈希，16个失败步骤准确分类为14日志断言缺失（exit0）与2真实非零退出。对原29个结构化建议仅在分析脚本中显式把旧required_output改名为同语义stdout_contains，不自动解释为文件检查：28个可解析（含4个原目录尾斜杠拒绝），原阶段逆序1个仍拒绝。该分析不执行构建、不证明原14个步骤或旧任务最终能成功，不回填旧结果；它复用新schema，属于开发回归，不冒称第二实现独立效果验证。

## 验证、证据与边界

新针对性回归28项通过；产品2116passed/44skipped，Ruff检查与格式通过。pytest退出后的旧临时目录权限清理警告保留日志，与本轮门禁实际容器清理分开，不修改旧临时数据。工程检查不代替科研效果。

- v2 raw：`/home/yiwei/.codex/outputs/forge-plan-predicate-qualification-v2/`；v1 raw同目录前缀的v1。
- 当前协议：`benchmarks/manifests/cpp-build-plan-predicate-qualification-v2.json`及同名preregistration；v1协议保留。
- 独立审计入口：`scripts/forge_audit_plan_predicate_gate.py RAW_ROOT NEW_RECEIPT.json`（使用backend uv Python；只读raw，不导入Forge执行器/Workflow）。
- 会话审计与日志：`/home/yiwei/.codex/outputs/forge-plan-predicate-session-2026-10-20/`，包括`interrupted-v1-independent-audit.json`、`historical-feedback-regression.json`、`independent-v2-audit.json`、`path-observations-independent-audit.json`、产品/门禁原日志及最终发布和知识库收据。最终CI/合并状态以GitHub及发布收据为准。

本轮仅支持新观察/纠错接口的工程资格，不支持真实模型更少犯错、自然恢复率提高、总体成功率或成本优势。保留#544全部失败与未知费用/未观察，旧HTTP402根因仍未核验。硕士主线继续，允许小幅/条件性收益与明确取舍。

下一步冻结新身份做小规模真实配对比较，按成功率、无效交接、恢复及全成本共同判断；两Workflow共享新合同，强工具作为整策略参照。会话中12槽草案仅设计、未冻结或授权。启动前需解决HTTP402外部阻塞，并核验新的身份/费用上限/有效时窗/停止规则，不能挪旧余额或续旧身份。接口稳定后再补C++项目效果样本，当前C++开发资格不扩大旧六C库效果结论。
