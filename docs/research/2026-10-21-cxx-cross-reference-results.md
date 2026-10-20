# C++ Make/Autotools完整参考资格

Issue #565；来源为#561固定tinyxml2@321ea883b7190d4e85cae5512a12e5eaa8f8731f与libconfig@a42cb47c1526a4f2ed025fcbb2289863375bc898。已见开发参考、非holdout；libconfig是C/C++混合库。本轮0Provider/凭据/模型Token/费用，原UTC22:07:35绝对截止不延长。

## 原双项目参考身份

cpp-build-cxx-cross-system-reference-v1为1/2qualified、0未观察。复用原Workflow、固定源码归档、同镜像2CPU、原文件SHA/索引/no HEAD、精确静态交付/clean replay与实际cleanup；没有改裁判来提高成功率。

| 项目 | 原执行与replay实际作者测试 | 工程交付/replay | 原文件不变 | 参考资格 |
| --- | --- | --- | --- | --- |
| tinyxml2 / Make | 各508 Pass、0 Fail | libtinyxml2.a精确通过 | 273文件全部保持 | 合格 |
| libconfig / Autotools | 各8 PASS＋原C++ example4 XFAIL、16/16 tinytest | libconfig.a和libconfig++.a精确通过 | 仅ac_config.h.in改写 | 不合格 |

libconfig不能称功能错误。原供应header模板含需要的宏，bootstrap阶段AUTOHEADER=true autoreconf -i未改它；configure生成Makefile时AUTOHEADER回到missing autoheader，后续make按时间戳重生成模板。独立原/replay全部原文件复核均只有ac_config.h.in改变；原完整测试和精确交付工程通过不覆盖这个操作合同。原失败保持，不续跑、不还原原文件、不豁免SHA检查。

raw /home/yiwei/.codex/outputs/forge-cxx-cross-system-reference-v1；inventory 9f68befdd78f290de50110ec718bdb6668adebf10a33d4f41a983897991555ab（2736文件/4链接/72181238bytes），运行release05503b2c4dce4f7aaeeec05d0d3d3e0c08483958。会话forge-cxx-continuous-session-2026-10-21/cross-reference-independent-audit.json及cross-reference-libconfig-details.json分别核验资格/源码合同与失败槽完整测试；实际cleanup均通过。前述508是断言计数，9是Automake入口、16是tinytest测试，不能混为同层样本。

## 独立header环境资格准备

新cpp-build-cxx-cross-system-reference-header-v1仅原libconfig一槽。唯一变化为configure前缀AUTOHEADER=true，延续已冻结bootstrap的供应模板选择；来源、完整测试命令/输出要求、上游XFAIL、两静态交付、原文件SHA/索引/no HEAD与replay/cleanup逐字段保持。原configure明确AUTOHEADER=${AUTOHEADER-...autoheader}，修订不删除或更改模板、不忽略测试/编译失败。若仍改原文件照常拒绝。

新174组件、同名manifest/preregistration；原171组件不改。独立header-v1已1/1qualified、0未观察，原/replay原文件265项全部保持；作者完整8PASS+1XFAIL、16/16 tinytest、两静态库精确交付、索引/no HEAD、同镜像2CPU重放与实际cleanup均独立审计valid。raw forge-cxx-cross-system-reference-header-v1，inventory c22ffdac89586ec8f7507d0d3a5a34c97ef84870bef422c9a7c70d3980b30a6c（1579文件/4链接/55427368bytes），运行releasec5d80fc33fd0341001bf74ebd6a88618ee215829。会话header-reference-independent-audit.json及其独立实现保留；新14组合测试/产品2225passed44skipped27warnings、Ruff通过。

有效参考池分别引用tinyxml2原身份与libconfig新身份，不称原双项目2/2；共同接口/真实三策略仍须新资格闭合后另冻，不加P2或改RQ3历史分母。资格只证明这些已见任务可严格完成，不证明真实Agent效果或跨系统普遍成功率。
