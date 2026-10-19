# 恢复planner的早期交接诊断门禁修复

Issue #526；工程修复组件资格，0Provider/新构建。#524在dep超时后提前读取测试日志导致FileNotFoundError，遮盖真正停止阶段；v1脚本/manifest/raw保持冻结不变。

新增`scripts/forge_build_libverto_recovery_planner_v2.py`，供后续**新身份明确接线**：先检查当前revision/hash，再判断是否固定check失败交接；非check交接立即给出PlanContractError且不接触源码目录。对check交接先验证test-suite.log/config.log存在，之后复用已冻结的单项configure修订判定。不增加自动重试、不修改测试/源码/交付、不改变已有时限；当前v1 runner不自动切换。

四项新增回归覆盖：dep交接且无日志时完全不访问source_root、合法check交接缺日志给明确合同错误、陈旧hash在读文件前拒绝、六断言完整诊断仍返回唯一configure修订。与原七项修订前提回归合计11 passed，Ruff/format通过。pytest清理旧临时目录时有历史权限警告，测试退出0；未修改这些旧目录或证据。

该修复解决的是下一次资格的失败分类与前提读取问题，不解决60秒依赖安装不足，也不证明libverto最小配置恢复已成功。后续必须在新的有效执行窗口下冻结足够依赖预算、明确使用v2 callback及其组件hash，完成同源初始失败→修订→完整测试/失效/replay资格；当前不重新运行v1、不补跑#504、不增加模型支出。

本轮UTC22:45后仅发布/知识库/资源/费用交接，23:00停止。此处只增加工程资格，不计为新增科研效果或论文创新点。
