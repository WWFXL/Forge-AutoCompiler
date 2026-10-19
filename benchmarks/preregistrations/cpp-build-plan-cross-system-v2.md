# 跨构建入口真实走读 v2：输出截断修复

跟踪 #478，总授权 #470。独立身份 `cpp-build-plan-cross-system-v2`，不重开或替换 v1。类型：探索性开发接入，不是效果比较。父 v1 inventory `2704868289b629da81532b0c8d91a15caf1d742b04cd41cede11c638a21dbc12`；失败报告 `docs/research/2026-10-20-build-plan-cross-system-v1-results.md`。

复用 v1 的固定 zstd/libusb 顺序、源码commit/tar哈希、镜像、材料包、全部测试、精确产物、clean replay及cleanup合同；逐项任务以本identity manifest为准。不得改源码测试、关闭udev、跳过stress_mt或替换四项make check。正负结果均保留，不要求libusb必须成功。

仅工程变化：同 DeepSeek Pro thinking/low，输出上限从8192提高到32768，单次timeout从120提高到240秒，SDK重试仍0。响应先保存并记完整usage；finish_reason=length或无结构化调用立即停止。结构化格式错误不由ToolStrategy隐式重试；不携带失败推理续问。原源码/日志材料不足仍可能失败，不注入助手手工修复方案或个人知识库。

每项目最多12请求，Token准入400000、单响应设计上界50000；Workflow32命令/2次交接/900秒，单命令180秒、replay300秒、cleanup60秒、2CPU。每项目已知估算+未知预留最多$2，阶段最多$4，共享用户$20。每次下一完整请求预留$0.40：60000 UTF-8字节消息即使逐字节token，加结构化schema及32768输出，按不高于100000设计tokens的高单价$3.96/M为$0.396；实际响应受50000 recorded tokens合同约束。无法完整计量时保留$0.40并停止该项目及后续项目。阶段先保留$4，结束封存后才按已知+未知结算。

截止UTC2026-10-19T23:00:00（北京时间20日07:00），请求截止22:45，每项目/每请求还需1800秒余量。不得因跨午夜顺延。凭据读取和调用前验证冻结组件/manifest、共享授权/预算、源码以及门禁；运行中不修改组件，原始create-once证据和失败只读。

门禁：实际LangChain图中截断、无方案和错误schema均一次请求、完整usage、无第二请求；相关回归及Ruff通过，再执行独立零Provider Docker接线。脚本化结果和模型结果分目录。完成后独立只读核验inventory、请求响应与usage守恒、固定任务、Session终态和cleanup。

仅支持修复后的已见开发项目接入观察，不支持成功率、跨项目泛化、选择器增量或成本下降。阶段结束后优先构建有真实测试与失败机会的来源资格目录及公平对照，不在已见项目反复抽样求成功。
