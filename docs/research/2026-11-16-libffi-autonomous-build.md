# libffi从零自主构建单例结果

日期：2026-11-16；Issue #756。身份 `cpp-build-libffi-autonomous-flash-v1`；[执行协议](../../benchmarks/preregistrations/cpp-build-libffi-autonomous-flash-v1.md)。类型：真实模型数据采集与案例分析。

## 结果

在没有人工修复提示、旧方案或经验注入的情况下，Forge自主完成了本次libffi主要库构建、交付与干净重建，原源码/测试保持不变。不过Agent没有找到缺少`libltdl-dev`这一原因，而是生成外部兼容宏，并将符号前导下划线检测值固定为`no`。当前主构建及交付标准记录为通过；这种替代宏的语义等价性、完整功能与跨平台适用性本轮未验证。

| 项目 | 观察 |
|---|---|
| 独立运行 | 1次，0重开/服务自动重试 |
| 初始规划 | 9请求，72.36秒，估费0.0436254美元 |
| 两次恢复合计 | 46请求，429.65秒，估费0.2629050美元 |
| 主构建 | 通过，约536.17秒达到主构建终点（含规划和恢复） |
| 静态/共享库交付 | 通过，`libffi.a`、`libffi.so.8.1.4`及运行库别名 |
| 实际干净重建 | 通过，34.03秒 |
| 源码/测试与清理 | 原输入不变，session completed，4个容器名称/ID引用确认不存在 |
| 总耗时 | 573.92秒（9分34秒） |
| 模型与用量 | deepseek-flash，55响应；699660输入＋80527输出＝780187Token |
| 费用 | 保守估费0.3065304美元，未知用量0 |
| 完整作者测试/库可执行入口 | 不要求/不适用，不填写测试通过 |

输入0.30、输出1.20美元/百万Token，按全部输入缓存未命中估费，不等于实际账单；所有初始/失败/恢复请求计入。用户授权新增1美元/确认起1小时，UTC2026-11-16 01:52:26—02:52:26；约02:02结束，无追加付费。

## 实际流转

同E57固定libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`、同原始归档及镜像 `sha256:8123220a201ac4d00cda0dc985b9db7227cd909bb93ca6c25fd82cafce5cd887`。运行代码 `e785c5dc66beaf247cb6995bc7f06e567679b138` 已包含PR755装配修复。P0初始规划、初始工具执行约束、规则路由、原R2恢复；未读取同项目成功配方或经验，独立reference不进规划上下文。入口自身只加载固定公开任务/参考/源码指针与通用R2，旧任务材料中的参考动作不传给Agent。

1. **从零规划，9请求。** Agent读取作者README、autogen、Makefile及configure输入，提交四步：检查并在缺失时安装构建工具 → `./autogen.sh` → `./configure` → `make -j2`。Workflow执行依赖检查成功，autogen实际报`LT_SYS_SYMBOL_USCORE`未定义。
2. **第一次恢复，43请求。** Agent反复读取源码/日志，推测系统Libtool不再导出该宏，未定位宏所属的开发包。在`/workspace/dependencies`新增兼容m4并用`ACLOCAL_PATH`引入；方案包含尝试通过编译和nm检测下划线的宏体。它被结构装配接受，但宏体heredoc内的`rm -f conftest.*`被现有命令删除保护识别，执行前返回126。该失败和原响应完整保留。
3. **第二次恢复，3请求。** Agent移除包含删除动作的检测逻辑，将宏的检测缓存值固定为`no`，重新提交方案。外部宏写入、带`ACLOCAL_PATH`的autogen、默认configure及make全部成功。成功依赖沿用，未发生历史依赖装配拒绝。
4. **交付与重建。** 系统独立定位真实静态/共享库、精确暂存，再用同镜像和原归档在新容器执行成功配方；实际通过后完成资源清理。配方不包含原失败autogen或被拒绝的第一份兼容宏命令。

最终关键恢复指令片段（原文见`libffi/agent/simple-actions-3.json`）：

```sh
mkdir -p /workspace/dependencies/libtool-m4compat
cat > /workspace/dependencies/libtool-m4compat/lt-sys-symbol-usc.m4 <<'M4'
AC_DEFUN([LT_SYS_SYMBOL_USCORE],
[AC_REQUIRE([LT_PATH_NM])dnl
AC_CACHE_CHECK([for leading underscore on symbols], lt_cv_sys_symbol_underscore,
[lt_cv_sys_symbol_underscore=no])
sys_symbol_underscore=$lt_cv_sys_symbol_underscore
AC_SUBST([sys_symbol_underscore])
])
M4
ACLOCAL_PATH=/workspace/dependencies/libtool-m4compat ./autogen.sh
# 后续独立阶段：./configure；make -j2
```

## 原因分析与研究含义

**执行闭环本次可自主完成，依赖诊断仍不准确。** [上轮工程诊断](2026-11-16-libffi-recovery-assembly-repair.md)已实际证明原Libtool2.4.7仍由`libltdl-dev`的`ltdl.m4`提供该宏，补包即可；本轮Agent“宏被移除”的判断仍然错误。外部生成文件没有改原源码，符合本轮文件保护检查，但硬编码检测结果不能据此证明等价于作者原工具链。保持观察到的通过标签，同时记录采用的修复内容，不将其表述为正确定位并补齐依赖。

**成本主要来自恢复探索。** 初始9请求，第一次恢复43、第二次3；恢复占总模型估费85.77%，约占总耗时74.9%。工具调用包含71次源码读取、11次目录枚举、6次日志读取；全部88次。当前恢复工具以源码/日志的定长读取为主，没有容器软件包/系统宏定义查询工具。恢复上下文多次压缩，长时间分段读取与重复猜测共存；本例支持优先改善诊断信息获取与证据保留，不能只凭这一次把开销归因为模型、压缩或某一组件。

**命令保护也影响了选择。** 第一次兼容宏里的删除文本位于heredoc，尚未作为Shell删除执行就被拒绝。随后Agent采用了更简单的硬编码宏。该时序已观察，但没有对照，不能断言若不拒绝就一定采用正确检测或更优方案。本轮不修改保护逻辑、不调整验收，也不追加验证运行。

本例只回答这个已知项目在当前环境中一次是否能自主走完。它不是新项目holdout、成功率估计、R2增量或PR755修复因果对比；原E57的失败与10/12、11/12、10/12保持。未修改论文或自动纳入正文。下一决策可基于此例讨论恢复Agent的诊断工具与不确定性处理，本轮不自动启动新比较。

## 证据与验证

- [精简摘要](../../benchmarks/analyses/libffi-autonomous-flash-2026-11-16/summary.json)，SHA256 `331ace388d5511826d76eb164465ef886b01a250abf5c3ce37c9ce21f57c1245`。
- 原件 `/home/yiwei/.codex/outputs/forge-libffi-autonomous-flash-2026-11-16-v1`：授权、scope、运行源码快照与哈希、55份模型请求/响应、事件计量、三份方案、实际命令与日志、交付产物、干净重建及清理。
- 类型化封存1513普通文件/8链接/31381166字节，inventory `72e0d6aa80913056b0e1482030e06331dddd65d73f36121e253199e776c38d7c`。55响应逐项复算与summary费用一致，未知0；构建/重建4个名称或ID均实查不存在。
- 入口材料/归档/R2检查、Ruff及真实运行通过；未修改生产编译代码，不为结果另跑产品全测。发布CI与合并以PR757最新head为准。个人知识库不进入正式Agent上下文。
