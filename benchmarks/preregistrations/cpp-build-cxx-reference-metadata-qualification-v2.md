# simdutf源码索引容器所有权资格 v2

Issue #554，零Provider/凭据/模型Token/费用，原截止不延长。父metadata-v1在最初dependency执行git add前被Git dubious ownership保护拒绝（exit128）；configure/build/CTest/交付/replay均未观察，原源码及实际cleanup通过。父身份28ff9d2e库存保留，不续跑/回填。

新身份只在父dependency的git init与git add之间插入`git config --global --add safe.directory /workspace/repo`，仅临时compile/replay容器内确切目录，不用通配符，不写宿主Git配置。原源码、主commit、来源图、配置、测试/全部marker、交付、预算和截止原样保持。全新Session一次，无自动重试。

与metadata-v1同样要求check_feature_macros在原/replay实际Passed、CTest94项实际执行且无skip，FAST_TESTS=OFF；真实ar、完整交付集合/类型/大小/hash、源码和实际cleanup仍须通过。目录信任不替代来源hash校验，不创建伪commit。新项3300秒余量，UTC2026-10-20T18:19:33Z截止；失败保留，不把工程准备失败当模型效果。
