# 新来源资格 v1：执行闭合，封存未通过

Issue #482；身份 `cpp-build-plan-source-qualification-v1`。四个预定参考任务 miniz、md4c、pigz、libite 均执行了固定原始测试，严格产物和clean replay通过，Session completed、cleanup成功，原始普通源码/测试逐文件哈希未变，0Provider。libite为21/21测试；md4c使用完整上游Python入口，而非空CTest。它们仍是参考方案资格，不是模型或方法效果。

阶段最终封存审计失败，因此决定为 `stop_for_seal_infrastructure_repair`，不能按该identity声称完整资格通过。原始目录 `/home/yiwei/.codex/outputs/forge-source-qualification-v1/`，保存了1742 files / 46,424,103 bytes 的inventory，canonical SHA-256 `23dbc8de5a17b6eb3ef48f083de1d154e705a0fbbf9a4b24118e2be335cba46d`；这个哈希存在不等于审计有效。

原因：libite的`autogen.sh`调用`autoreconf -W portability -visfm`，其中`-s`使工作区和重放源码中的28个生成辅助文件成为指向`/usr/share/automake-1.16/`、`/usr/share/libtool/`的符号链接。旧封存器记录了其读取内容，但只读审计拒绝解析到证据根外的路径。独立外部分析未发现这些条目的内容哈希/大小变化；28项均为`resolved_outside`，分析文件 `/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/source-qualification-v1-seal-failure-analysis.json`。没有改写原inventory、seal或链接。

下一步 #484 建立独立v2，libite bootstrap 使用同工具、同功能且安装辅助文件副本的`autoreconf -W portability -vifm`，去掉`-s`。固定源码、测试、产物、镜像和验收不变，四项全部重跑；不通过放宽审计或复制外部数据回填原证据来挽救v1。只有新身份完整执行与封存审计均通过，才能进入后续比较设计。
