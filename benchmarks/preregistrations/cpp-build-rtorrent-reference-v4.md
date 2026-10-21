# rtorrent自包含验证脚本独立参考v4

2026-10-21，Issue581。v3原12程序全部退出0且323叶精确身份/总数通过，交付rtorrent -h也返回0并输出0.16.25/Usage；但最后汇总json.dumps因生成子进程脚本缺局部import json而NameError，严格步骤失败，replay未观察。封存原失败，不能改为qualified或续旧工作区；独立审计只记录实际原测试/CLI，不回填外层步骤成功。

v4仅在verification_main内显式import json，使inspect.getsource生成的脚本可自包含执行。新增回归实际在空globals下执行生成的python -c内容，替身进程/路径按成功原测试和CLI契约返回，核验完整汇总与每次调用；此回归不是上游真实测试。其余v3的精确323叶/12程序、全部818原文件、40生成SHA、完整依赖/镜像、默认功能与断言、无网络/2CPU、精确两ELF/CLI/replay/cleanup均继承。

新原/replay均空目录，仅一次；0Provider/凭据/模型费。原执行1200秒/replay1200秒/准入2700秒/单命令1200秒、32命令0handoff；原UTC07:26:27截止不延长。新组件/manifest先测试冻结提交，旧冻结组件与全部失败证据不改。只支持任务资格，不称模型效果、自然恢复或holdout。
