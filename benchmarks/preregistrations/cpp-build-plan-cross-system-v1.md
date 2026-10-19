# 跨构建入口规划与真实失败走读 v1

跟踪 #476，总授权 #470。类型：探索性开发走读，不是效果实验。源码和方案生成规则在首次 Provider 调用前冻结。

## 问题与样本

同一结构化方案、状态执行、失败交接与严格验收链路，能否在已见的 Make/Autotools 项目上工作？真实失败是否能保留足以判断下一项研究问题的证据？

固定顺序：zstd v1.5.6 / `794ea1b0afca0f020f4e57b6732332231fb23c70`，libusb v1.0.27 / `d52e355daa09f17ce64819122cb067b8a2ee0d4b`。复用已核验源码归档作为输入，重新导出根即源码根的 tar 并绑定哈希；旧 evidence 不修改、不补填。两者已见，不能当 holdout 或自然失败总体。

镜像 `sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`，每会话2CPU，命令180秒、Workflow900秒、重放300秒、清理60秒；最多32条命令、2次恢复交接。安装依赖只限隔离容器，不挂载凭据。源码包不含.git、知识库或历史配方。

## 输入与固定验收

模型使用既有DeepSeek Pro thinking/low，8192输出tokens、timeout120秒、SDK重试0。只允许PlanProposal结构化输出，不能直接执行Shell；模型查看预注册路径的有限源码包和真实失败交接，不接收本次助手的修复建议。每次源码包最多36000 UTF-8字节，文件带完整哈希、行号和截断标记。不是开放工具型Agent实验。

zstd材料：README.md、Makefile、lib/Makefile、tests/Makefile、programs/Makefile。任务交付`libzstd.a`，固定`make check`和上游实际输出标记`frame concatenation tests completed`；这是上游basic/shortest测试，保留其原有跳过项，不称全量上游测试。

libusb材料：README、INSTALL、configure.ac、bootstrap.sh、.github/workflows/linux.yml、tests/Makefile.am、.private/ci-build.sh。任务交付`libusb-1.0.so.0.4.0`，固定`make check`全部四项，要求`# TOTAL: 4`与`# PASS:  4`。保存`tests/test-suite.log`及四项内部日志；不允许跳过stress_mt、改源码测试、关闭udev或改变验证任务。此限制用于保持此前开发任务，失败可成为有效的未闭合观察。

原始测试、精确产物集合、既有结构验证、clean replay、重放测试、大小/类型/SHA-256和cleanup均通过才记completed。每个成功、失败或预算终止都保留；不要求为了交付而把两项目都修到成功。

## 预算、停止与证据

阶段最多24次请求，每项目最多12次；每项目Token准入400000、单响应设计上界50000，最多450000设计tokens。每项目已知费用加未知用量预留不得超过$2，阶段最多$4，计入共享$20；初次意外live测试$1另行保留。

每次Provider准入额外按$0.40预留下一响应（高于冻结60000字节上下文、结构化工具schema、8192输出和协议开销的100000 tokens保守价上界$0.396）。API失败且usage未知则保留该$0.40并停止该项目，不自动重试。已知费用用冻结峰时价input $1.32/output $3.96每百万token估算，不声称实际账单完整。

阶段先在共享账本保留$4，只有完整结束且逐请求核验后才能释放未用预留。不得并行启动其他付费阶段。开始项目和每次模型请求均需距06:45请求截止点至少1800秒；因此最迟06:15不再启动请求，为最坏执行、重放与清理保留余量，07:00前完成交接。

先跑零Provider的材料边界、预算/截止、验收不变与工具接线测试，再用脚本化响应对两个真实项目执行接线门禁。门禁失败属于工程证据，不混入模型结果；修复后重新运行独立门禁输出，不修改旧结果。真实试运行每次新建create-once目录，代码与manifest哈希绑定，封存inventory和seal；失败后若继续须新版本，旧结果只读。

不估计处理效应、显著性、一般成功率或成本节省。下一研究决策取决于是否出现可重复的状态/动作分歧；仅规则能处理的状态不包装成复杂选择器优势。

## 首次付费运行前的工程门禁观察

独立`forge-cross-system-gate-v1`的脚本化门禁：zstd原始构建/测试、clean replay和清理通过；libusb原始构建成功，四项测试中stress_mt失败，内部日志记录八线程`LIBUSB_ERROR_NO_DEVICE`，cleanup完成。其原始结果和封存manifest只读，不作为模型结果；不能回填旧走读缺失日志。

发现无读取工具的恢复模型需要直接接收已采集内部日志，因此在首次Provider调用前增加哈希绑定、最多五份/每份1200字节预览的诊断材料包，并重新执行独立接线门禁。源码包、样本、固定测试与验收不变。源码与测试不允许被方案改写，运行中逐文件检查原始源码哈希。真实libusb若仍未闭合，保留失败，不以减少测试换取完成。

第二轮`forge-cross-system-gate-v2`再次得到zstd严格完成、libusb相同四项测试失败并清理，封存inventory为`d34f39d43d9168546c03c07f9ac3b2c7721f34a8b72dbbe192069f7a101e5d99`。将其实际日志按runner同样规则压缩为最近三条命令/每条2000字符，五份内部日志可在真实结构化图中零Provider回放，序列化请求54801字节，小于60000上限；未压缩的诊断回放被上限拒绝并保留，不作模型观察。根据实际生成config.h，后端核验使用`HAVE_LIBUDEV`宏（不是Automake的`USE_UDEV`条件名）。这些修正均在首次付费运行前完成，旧门禁代码快照不改写。
