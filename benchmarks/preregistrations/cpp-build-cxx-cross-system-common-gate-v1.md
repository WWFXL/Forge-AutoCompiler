# C++ Make/Autotools共同接口六槽零Provider门禁

Issue #568。固定tinyxml2 Make（原reference-v1合格）和libconfig Autotools（独立header-v1合格），各工具规划Workflow、模型规划Workflow、强工具Agent一次，共6槽。参考已经向开发助手暴露；均为development资格、非holdout；libconfig为C/C++混合库。

仅把显式task.build_system选择扩展到唯一普通Makefile/makefile/GNUmakefile，保留不安全/多Make入口/已有同名产物拒答。其他系统沿用原任务选择器；libconfig多入口Autotools仍拒答转脚本模型，不猜bootstrap/开关/依赖，不按项目名绑定命令。所有方法共同引用材料meter、来源准备、完整固定测试、精确暂存、同镜像2CPU重放和cleanup；参考只供Fake资格，不进入未来真实Agent。

tinyxml2工具模板预期0Fake严格完成，模型Workflow/强工具各1Fake；libconfig工具拒答后1Fake、模型Workflow/强工具各1Fake。只验证工程接口，不把5脚本响应当真实效果。原供应header、完整8PASS+1XFAIL和16tinytest、tinyxml2完整508断言所对应自测不删改；固定测试命令来自已合格参考，装配后仍须逐字段保持。重复源码准备不允许，原/replay索引/no HEAD及全部原文件SHA保持。全部Provider/凭据/模型Token/费用为0。

本轮原UTC22:07:35截止和3300秒新槽预留不变，串行Docker，每臂原32命令/2handoff约束，单执行600秒/replay900秒；无重试/替换/补槽，cleanup失败停止，未观察保留。六槽实际完整闭合且独立审计通过后才能冻结付费候选；本门禁不证明方法优势。不改变旧RQ3分母/主线/裁判，不加P2。
