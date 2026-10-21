# rtorrent完整测试与交付smoke分离独立参考v5

2026-10-21，Issue581。v4原执行及干净重放脚本均完成12程序323叶和交付CLI，构建/verify退出0；但最终产物smoke将全套测试命令作为functional command再次执行，其默认20秒不足，故attempt timed_out/Session failed、cleanup成功。该约570秒事件不是1200秒replay总时限耗尽，不改判旧失败。保留真实叶观察与未完成的最终验证。

v5只修正可信证据绑定：保留v4的full-author-tests步骤（完整323叶与CLI），另增delivery-cli独立smoke步骤，执行LD_LIBRARY_PATH=/artifacts /artifacts/rtorrent -h；要求退出0、原0.16.25和Usage。提交配方显式包含全部测试与独立CLI两smoke步骤，rtorrent的ExecutableVerificationPolicy只绑定独立CLI记录，从而最终20秒产物smoke只重放快速CLI；不删除完整测试，不延长smoke或整体时限，不改产品默认策略。

原v4合同及818源码/40生成SHA/依赖镜像/包清单/默认功能/精确两ELF/全部测试/cleanup继承，原及replay均空目录一次，0Provider/凭据/模型费。原执行1200秒/replay1200秒/准入2700秒、单命令1200秒、32命令0handoff及2CPU无网络不变，UTC07:26:27截止不延长。新runner/接口回归/manifest先冻结提交，原失败永久保留。仅任务资格，不称策略效果。
