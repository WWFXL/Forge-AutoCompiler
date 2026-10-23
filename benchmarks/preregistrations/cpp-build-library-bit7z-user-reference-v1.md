# bit7z普通用户测试上下文独立资格

Issue625；cpp-build-library-bit7z-user-reference-v1；0Provider/凭据。旧root参考首程序572case/1失败（13断言），当前镜像已有ubuntu uid1000/home/ubuntu；原tests/src/utils/filesystem.hpp以真实用户HOME取userDir，而test_fsutil.cpp1276在该目录测试父目录..。root的/root父目录为/使ZipSlip反例退化。

前瞻冻结新身份：构建/源码/依赖/配置/三个原程序/所有默认测试/断言/精确libbit7z64.a/clean replay/cleanup不变，只在固定smoke前确保镜像原普通用户目录存在并赋予源码目录写权限，runuser --user ubuntu运行原Python测试驱动。使用正常用户上下文，既不覆盖HOME变量也不修改任何源或测试字节。此设置也使作者root跳过分支按普通用户实际执行，不将原root未执行分支记通过。失败照实保留，无自动重试，旧身份不续跑。

一次完整新参考和clean replay，沿原2CPU/同镜像/主1800秒/命令1200/replay1800/新项目3900预留，原UTC09:27:52截止不延期。为避免占用CPU干扰付费比较耗时，待当前12槽终结后单独运行。是否有资格由全部原测试/源保护/交付/replay/清理共同决定，不按参考结果改计数或过滤。不能补入原12槽或用root→普通用户跨身份差异声称方法收益；后续若比较须另冻共同任务，不称零辅助任务或holdout。
