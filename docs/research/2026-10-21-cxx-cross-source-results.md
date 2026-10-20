# C++跨Make/Autotools来源资格

基础设施阶段，cpp-build-cxx-cross-system-source-v1。补当前新增C++样本全为CMake的来源缺口；不执行源码，不是构建或方法成功率。固定tag/commit后采集公开metadata/commit/完整tree及codeload，首失败即停、不替换项目/补跑。

| 项目 | 固定commit | 拟任务 | 普通文件/链接 | 来源结果 |
| --- | --- | --- | --- | --- |
| tinyxml2 | 321ea883b7190d4e85cae5512a12e5eaa8f8731f | make | 273/0 | 精确Git对象对应通过 |
| libconfig | a42cb47c1526a4f2ed025fcbb2289863375bc898 | autotools | 265/0 | 精确Git对象对应通过 |

2/2来源通过、0未观察。压缩归档只去外层目录，字节/执行权限/链接文本保持；逐blob内容/模式对应完整递归tree。独立stdlib审计另从Git树条目重建每个tree对象，根SHA精确等于固定commit指向的tree；归一化前后文件/模式/链接逐个一致，原始归档/metadata/树和源代码快照均封存。
首版审计误认为按commit查询tree的API响应sha必为根tree SHA，因API实际回显请求commit而拒绝；保留失败审计代码hash/原因收据，修正为独立完整Merkle树对象重建后通过。没有修改、重跑或再下载原始身份，不把审计器错误算来源失败。
封存inventory 89e09bc2267593695a0dae54f9eda9d764d0afcc3af7ad780850d92c4f6aff5f，186文件/0链接/15686794bytes；168组件、manifest SHA ea3f33fd6d66870fcb667125cd90b5bbab839a0a9b6e8429dd44cc87fd65b95c，运行release575c74cd。raw /home/yiwei/.codex/outputs/forge-cxx-cross-system-source-v1；独立审计cross-source-independent-audit.json及实现/失败元数据/唯一启动位于会话forge-cxx-continuous-session-2026-10-21/。

## 作者入口与后续边界

开发助手已读固定作者Makefile、README、configure.ac与测试Makefile.am/CI；tinyxml2 Make默认xmltest+静态库，make check执行原自测；libconfig Autotools包含C/C++示例及tests程序，C++example4原XFAIL必须保留。仅说明原文件内容，实际构建/完整测试数/源码不变/精确交付/clean replay/cleanup均尚未观察，不能据来源通过把参考或策略标为成功。
后续单独冻结原作者完整测试、C++功能与精确静态交付参考资格；源码/索引/no HEAD/同镜像2CPU/原与replay测试/清理不放宽。libconfig为C/C++混合库，不能当纯C++复杂仓库。源码/构建说明均已见，不声称holdout/训练未见/总体或自然成功率；不向未来真实Agent注入人工配方、论文/知识库。
0真实Provider/Provider凭据读取/Token/模型费/构建命令/Docker。gh只读公开元数据使用已有认证，不调整认证、网络、服务或daemon。本阶段沿本轮UTC22:07:35截止，不开付费stage，不干扰主工作区#560真实六槽或改变其HEAD/177组件。RQ3旧固定分母/主线/验收不变，不加P2。

## 检查与发布

8新针对性回归、完整产品2211passed44skipped27warnings及Ruff通过。独立工作区yiwei/561-cxx-cross-system-source；最终结果HEAD三CI全成功后仅合科研依赖分支，不进main。用户主工作区未跟踪HTML不触碰；GitHub发布状态以最终CI/merge/Issue561回读为准。
