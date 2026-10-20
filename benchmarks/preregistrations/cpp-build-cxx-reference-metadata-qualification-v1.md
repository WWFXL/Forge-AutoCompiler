# simdutf上游文件检查的源码元数据资格

Issue #554，独立cpp-build-cxx-reference-metadata-qualification-v1，零凭据/Provider/Token/模型费用。父缓存资格保持完整；其首轮CTest94注册项中93通过、check_feature_macros因归档无.git索引而以作者声明142跳过，不能称94项实际全通过。待父replay/cleanup/封存完成后才启动本身份，不并行重型构建。

仅复制父simdutf任务，在最初dependency命令追加`&& git init -q && git add --force --all`。这是原归档文件的本地Git索引准备，不创建伪造commit、不改主commit身份、不改原源码/作者测试，不新增联网克隆或软件包。force用于将精确归档中本来受跟踪的文件全部入索引，尚未生成build目录。

配置、完整CTest及所有marker字节、SIMDUTF_FAST_TESTS=OFF、镜像、交付、预算、截止全部保持；不删除/过滤check_feature_macros，不改其SKIP_RETURN_CODE。新干净Session一次；通过须同时核验check_feature_macros在原/replay实际Passed且无CTest跳过，原源码/真实ar精确交付/同镜像空环境replay/cleanup仍过。不能把仅CTest汇总100%当全部用例执行。

3300秒新项预留，UTC2026-10-20T18:19:33Z绝对截止不延长。父配置失败/跳过均保留，不续跑或替换旧身份；本项失败/超时也保留。本阶段仍是任务来源准备资格，不是模型恢复效果、方法成功率或创新机制证据；正式比较前要对全部策略统一固定源码元数据输入与完整测试合同。
