# 新增C++固定来源图准备 v1

Issue #554，0Provider/凭据读取/Token/模型费用/构建。父来源为cpp-build-cxx-source-qualification-v1，inventory a8c8936fe51abc525ce4076fe1ee1195ab20388e2ec6df6ffd4d16c43f186b7c。

保持yaml-cpp/simdutf/snappy三项与顺序，各读取仓库元数据及完整git tree，保存fork/parent/source信息和gitlink。yaml-cpp/simdutf预期无gitlink；snappy须精确匹配third_party/benchmark@b20cea674170b2ba45da0dfaf03953cdea473d0d、third_party/googletest@b796f7d44681514f58a683a3a71ff17c94edb0c1。依赖URL来自原.gitmodules，归档只下载一次、保持全部内容，不替换系统GoogleTest或关闭测试。未登记gitlink或截断树立即停止。

仅剥除codeload外层目录，依赖接入gitlink目录，普通文件字节/链接文本保持；不得覆盖原路径。保存依赖归档/索引、完整组合source.tar及普通文件hash。组合来源图与主commit分别标识，不能把组合归档冒充纯git archive。

共同GoogleTest属于测试基础设施关联，不证明项目族完全独立。当前有限精确owner/name历史无命中不证明训练、外部或全语义未见；源码及参考读取登记为设计暴露。截止UTC2026-10-20T18:19:33Z，失败/部分保留不自动重试，不执行下载代码。
