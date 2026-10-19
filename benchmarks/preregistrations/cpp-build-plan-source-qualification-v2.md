# 新来源零Provider资格 v2：自包含辅助文件

跟踪 #484，独立身份 `cpp-build-plan-source-qualification-v2`。父v1四项目实际strict完成，但28个Autotools生成链接解析到证据根外，使封存审计失败；原始目录、inventory、seal和失败保留，见`docs/research/2026-10-20-build-source-qualification-v1-results.md`。不修改封存器或放宽目录边界。

完整继承v1的固定顺序miniz/md4c/pigz/libite、exact commit、根tar哈希、镜像、完整原测试、精确交付和严格验收、每项目仅一次/无模型修复/无替换、600秒方案/120秒命令/180秒replay/2CPU和原绝对截止。唯一参考命令变化是libite bootstrap：从原`./autogen.sh`（autoreconf -W portability -visfm）改为`autoreconf -W portability -vifm`。去掉`-s`使同样的辅助文件安装为副本，自包含证据不依赖宿主同路径文件；不是关闭测试或改源码。

仍要求原始普通源码/测试哈希不变、完整测试真实执行、clean replay及精确产物一致、Session completed/cleanup、原审计器valid=true。四项目全部重跑，不把v1的执行结果回填成v2。全阶段0Provider/0凭据读取。全部合格才进入四项目比较设计，不作方法效果或泛化结论。新manifest、运行组件和父来源inventory在首次构建前冻结。
