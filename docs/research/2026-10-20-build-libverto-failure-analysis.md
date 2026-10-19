# libverto自然测试失败的只读根因链

Issue #522；身份`cpp-build-libverto-failure-analysis-v1`，结果分析，0新构建/Provider。来源仍为#504冻结真实探针`cpp-build-auto-provenance-probe-v1`的libverto-r2-plan，失败不补跑、不回填。登记`benchmarks/analyses/cpp-build-libverto-failure-analysis-v1.json`。

## 直接观察

父raw `/home/yiwei/.codex/outputs/forge-auto-provenance-real-v1/`，inventory `d7bad477a8b355ffdbb21de127961c2f8f639798186d6c7d6ad0ecb27263e446`。会话相对位置`libverto-r2-plan/.compile-sessions/plan-agent-canary/a3e997ddf706/`。

- 真实命令依次为依赖安装、autoreconf、`./configure --disable-shared --enable-static`、`make -j2`、固定`make check`，退出码0/0/0/0/2，没有超时。
- `workspace/repo/tests/test-suite.log`记TOTAL6/PASS0/FAIL6；timeout、idle、child、signal、read、write都在`test.h:74`同一断言失败：`ctx = verto_default(MODULES[i], VERTO_EV_TYPE_NONE)`，退出134。不是空测试，也不是六种测试逻辑分别报告不同失败。
- `config.log`实际`BUILTIN_MODULE=''`；生成的tests/Makefile DEFS没有BUILTIN_MODULE。src/.libs在父inventory中共12项，仅静态`.a`和Libtool元文件，没有`.so`；libverto.la和libverto-glib.la均`dlname=''`、`library_names=''`。

## 精确源码对机制的解释

六个引用源文件已与固定source archive逐字相等核验，非修改后的解释源码。

| 精确源文件及行 | 代码机制 | 对解释的作用 |
| --- | --- | --- |
| tests/test.h:35–54、71–76 | 按编译启用的后端列表创建上下文；成功后才进入do_test | 六测试共享前置条件失败，后续功能逻辑尚未开始 |
| tests/Makefile.am:2–18 | 测试链接核心libverto.la；MODULE_GLIB/LIBEV/LIBEVENT启用对应HAVE宏，固定六程序为完整TESTS | “只生成静态库即可完成测试”的方案假设需要额外检查 |
| configure.ac:83–100、154–159 | 只有显式builtin选择才设置BUILTIN_MODULE，普通后端以模块构建 | 此次没有内建后端，不能假定静态核心已含实际事件实现 |
| src/Makefile.am:10–54 | builtin分支把实现源加入核心，否则单独生成后端库 | 静态核心与静态后端文件存在，不等于运行时能自动发现后端 |
| src/verto.c:376–479 | 无builtin时通过核心符号位置推导模块文件路径和后缀，再加载模块 | 运行路径以动态模块发现为基础，与静态-only产物不匹配 |
| src/module.c:116–145、175–205 | dladdr获得符号所在文件，dlopen加载模块 | 仅编译/链接退出0无法保证运行时模块可加载 |

这些证据支持**静态-only、无builtin配置与默认动态后端加载路径不匹配**的机制解释，并将直接失败定位到上下文创建，而非测试难度或阈值过严。没有运行时分支追踪，不能断言每个进程具体在哪个return0分支退出，也不能把源码解释当修复反事实已验证。

## 对下一阶段的约束

候选修订是保留static并恢复shared后端构建；已有#493参考资格证明该固定源在完整任务下可运行，但它不是从当前失败计划只改单个选项的配对反事实。本阶段没有执行该修订，也没有证明单一选项一定足以修好。

后续若验证，从新身份、同源/镜像/任务出发，固定原计划与仅改变configure的候选，重新判定首变化后的build/测试凭证，完整make check、原源码、交付和clean replay保持；不能通过只选一个后端、关闭测试或改断言获得成功。即便修好，也只是该已见自然失败的后验恢复资格，不是自然恢复率或复杂选择器相对规则的增量。

这条状态对路由的启示是：首次日志只说明共享前置条件失败，尚不具备#516那样直接可绑定的错误字符串；先读完整test-suite.log与构建/加载源码再作候选。合理规则若未覆盖，应进入Agent调查；不据此必然引入学习型选择器。原#504确实已发出5次恢复请求、最终0修订，之后第10次总请求被材料门禁拦截；不能说未调用恢复，也不能归结为模型能力不足。

## 核验与边界

19个消费文件hash匹配父inventory，6个源文件与固定源归档逐字相等，归档SHA匹配父任务；上述命令/断言/构建产物事实用独立标准Python只读提取核对。分析登记含文件相对路径/hash、完整12项库目录inventory引用与观察。未重算父全部响应、未执行新测试或修改代码，父独立审计仍是原valid=true。文档/JSON变更经diff检查和最终head三项实际CI后发布。

共享费用不变，原失败/5次恢复的成本不删除。UTC22:45后仅清理交接，UTC23:00停止，不为验证该反事实越过本轮时窗。
