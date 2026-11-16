# 通用依赖诊断指导下的libffi自主构建观察

日期：2026-11-16；Issue #758。身份 `cpp-build-libffi-dependency-guidance-flash-v1`；[协议](../../benchmarks/preregistrations/cpp-build-libffi-dependency-guidance-flash-v1.md)。类型：单次真实模型采集与案例分析。

## 结果

追加通用依赖诊断原则后，Forge从零完成libffi主库、静态/共享库交付和实际干净重建，原源码/测试不变，资源清理通过。本次没有伪造宏或硬编码检测值，而是源码安装真实Libtool并补装Texinfo。不过Agent仍未定位系统缺少`libltdl-dev`，且恢复探索更长：67请求、864.48秒、保守估费0.3904869美元。提示更新改善了本次观察到的修复方式，尚未解决依赖诊断与效率问题。

| 指标 | 本次观察 |
|---|---|
| 初始P0规划 | 7请求，18.48秒，0.0276216美元 |
| 三次恢复 | 27＋23＋10＝60请求，723.97秒，0.3628653美元 |
| 主构建 | 通过，812.50秒达到主构建终点（含规划/恢复） |
| 交付 | `libffi.a`、`libffi.so.8.1.4`及运行库别名，通过 |
| 实际干净重建 | 通过，48.26秒 |
| 原源码/测试保护与清理 | 通过，session completed；4个容器名称/ID实查不存在 |
| 总体 | 864.48秒；67响应；837795输入＋115957输出＝953752Token |
| 保守估费 | 0.3904869美元；未知用量0 |
| 完整作者测试/库可执行入口 | 不要求/不适用 |

按输入0.30、输出1.20美元/百万Token、全部输入缓存未命中估费，不代替实际账单。用户授权1美元、确认起1小时（UTC02:31:47.865644—03:31:47.865644）；实际约02:46:14结束，无Provider自动重试或新增运行。

## 改动与输入

运行revision `09ae3ada3f07bacb996285feaf57c4399556b13e`，同E57的libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`、原始归档和不可变镜像。仅在原R2恢复指导末尾追加[通用诊断原则](../../benchmarks/fixtures/dependency-diagnosis-guidance-v1/guidance.md)：核查依赖提供者/路径/版本，以最小检查获取证据，不伪造宏或固定检测结果。恢复候选指纹`ba13941c9bf33b4eb595ee8a575e10a1266973862072f1401da5ae70f9f24c12`。

P0、初始工具约束、规则路由、恢复工具、Workflow、资源和验收保持；不提供具体包名、原失败宏名、旧轨迹或成功指令，不启用经验复用。真实恢复请求已核对包含新增原则。初始方案本次重新生成，因此与上轮的差异不能全部归因于恢复提示。

## 实际轨迹

1. **初始规划7请求。** 读取作者材料后提交`./autogen.sh → ./configure → make -j2`。autogen报`LT_SYS_SYMBOL_USCORE`未定义。
2. **第一次恢复27请求。** 反复读取源码与失败日志，观察到失败autogen曾生成configure，提出直接运行configure。修订装配时执行器清理生成文件，该configure已不存在，执行返回127。原失败和方案保留，没有人工补救。
3. **第二次恢复23请求。** Agent继续错误地将宏缺失解释为Libtool版本问题；最终提出在受管依赖目录下载、构建、安装Libtool2.4.7，再执行带PATH和ACLOCAL_PATH的autogen。四个真实依赖步骤成功，autogen与默认configure成功；make在默认文档目标因`makeinfo`不存在而失败。
4. **第三次恢复10请求。** 根据日志明确的命令缺失和Texinfo提示，增加`apt-get install -y texinfo`；保留已成功的Libtool依赖，不关闭默认文档目标。重新autogen、configure、make通过。最终交付和新容器重建全部通过。

最终关键动作（完整原文见`libffi/agent/simple-actions-3.json`、`simple-actions-4.json`）：

```sh
# 分别作为四个dependency步骤执行：下载/解包；配置；构建；安装
./configure --prefix=/workspace/dependencies/libtool
make -j2
make install
# 新增缺失文档工具
command -v makeinfo >/dev/null 2>&1 || { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y texinfo; }
# 三个主项目阶段
PATH=/workspace/dependencies/libtool/bin:$PATH ACLOCAL_PATH=/workspace/dependencies/libtool/share/aclocal ./autogen.sh
./configure
make -j2
```

## 为什么通过，为什么仍然昂贵

**真实工具链补全使构建通过。** 保留的安装目录实际含`share/aclocal/ltdl.m4`，其中定义所需宏。Libtool源码安装提供了这个真实文件，ACLOCAL_PATH将其送入宏搜索路径；无需伪造宏、降级或改原源码。[此前工程诊断](2026-11-16-libffi-recovery-assembly-repair.md)已证明同版本系统开发包也能提供该文件。Agent认为“宏由libtool.m4提供/旧版本已移除”的解释仍然错误；本次正确执行结果不能当作正确根因解释。

**恢复以重复读取为主。** 总111次工具调用：77次read_source、20次list_source、14次read_failure_log，恢复占105次。60次恢复请求和0.3628653美元占总费92.93%。当前恢复工具不能直接查询容器软件包/系统宏来源；提示虽允许在dependency步骤安排环境检查，Agent本次没有先生成这种可区分原因的检查，而是长时间推测。源码安装Libtool完成了补全，却比直接装开发包更重。

**生成文件生命周期也是一次额外失败来源。** 首次恢复依赖失败阶段生成的configure，执行器重置后文件消失。此例说明恢复方案应以可重建输入为依据，不能把失败阶段残留物当稳定前提。本轮只观察，不顺带更改执行器或保护策略。

与[上次原R2自主观察](2026-11-16-libffi-autonomous-build.md)相比，两次均通过现行构建/交付标准；本次从外部硬编码宏变为真实工具链，费用从0.3065304增至0.3904869美元（高27.4%），总耗时从573.92增至864.48秒（高50.6%），请求55增至67。两次独立初始规划、每条件仅一次、已暴露同项目，以上是描述性案例对照，不估计提示因果效应或总体成功率。保留两次完整结果，不回填E57，不改论文或产品默认。

本阶段到此结束。下一步可由用户决定是否为恢复Agent增加最小环境查询能力，并约束以实际证据支持依赖修复；本次没有自动启动该改造或新比较。

## 证据

- [精简分析](../../benchmarks/analyses/libffi-dependency-guidance-2026-11-16/summary.json)，SHA256 `25d4b8a9ff83c73737233bbb519472a5dd58ff8cc9a3c122fae92a914d200976`。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-dependency-guidance-flash-2026-11-16-v1`，含67请求/响应、4份方案、日志、交付、实际重建、授权与源码快照。
- 封存2202普通文件/20链接/62891940字节，inventory `d61a329034a135ac365702bb3dfec7a08ec61938f96e329aa6ffa1a0cf59f474`，类型化audit通过；67份响应Token/费用独立复算一致，未知0；cleanup-verification记录4个名称/ID不存在。
- 材料/归档/参考/指导Schema、Ruff、Docker条件及本次真实运行通过；未修改生产代码，不重复产品全测。发布状态以PR759最新HEAD三项CI及合并为准。个人知识库不注入实验Agent。

发布说明：PR初建时目标误设main，检查涉及历史格式差异；合并前已纠正为既有科研集成分支`yiwei/534-rq3-natural-failures`，实际变更11文件。不为此改无关测试文件、不发布到main；本次合并以纠正目标后的最终HEAD检查为准。
