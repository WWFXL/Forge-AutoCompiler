# 查询索引修复后的libffi自主构建观察

2026-11-16，Issue #774；真实单例数据采集与结果分析，结果先交用户审核，不修改论文。

## 结果

Flash从零自主规划，在真实缺宏后源码安装Libtool 2.4.6，使用其真实宏完成libffi主要库构建、静态/共享交付和原归档干净重建。没有伪造宏或固定检测值，454原输入的内容/权限/链接未变，186个新增生成文件保留后验审查记录。任务成功与依赖诊断正确分别记录：**构建成功，但仍没有找到系统开发包libltdl-dev，关于“2.4.7不提供该宏”的版本判断仍然错误。**

| 指标 | 观察 |
|---|---|
| 模型与实际响应 | deepseek-flash，10/10响应一致 |
| 初始规划 / 恢复请求 | 3 / 7；一次实际恢复、两份接受方案 |
| 输入 / 输出 / 总记录Token | 126325 / 13136 / 139461 |
| 初始 / 恢复估费 | 0.0123318 / 0.0413289美元 |
| 合计估费 | 0.0536607美元，未知用量0 |
| 累计墙钟时间 | 170.92秒 |
| 主库 / 交付 / 实际干净重建 | 全部通过 |
| 原作者测试 | 本次主要构建目标不要求，未执行 |
| cleanup | 通过，主/replay四个名称及ID实查不存在 |

费用按输入0.30/输出1.20美元每百万Token保守估算，没有抵扣缓存命中优惠；逐原响应与账本复算一致。

## 怎么做的

[协议](../../benchmarks/preregistrations/cpp-build-libffi-index-autonomous-flash-v1.md)、[入口](../../scripts/forge_libffi_index_autonomous.py)：原libffi commit `3d0ce1e6fcf19f853894862abcbac0ae78a7be60`及源码归档不变，简洁主要库目标、P0工具约束、R2通用依赖原则、规则路由、恢复查询v2、后验文件审查。不给依赖答案、旧方案、旧轨迹、成功经验或人工修复，从零独立规划，失败才进入恢复。

固定新查询镜像`sha256:d483ffa7b71b9545cff9555f6c92b6281a3f826ce006e2d09134cbdca92f8aa1`，有apt-file及Packages/Contents索引，无预装libltdl-dev。它与历史镜像不同，不把单例间费用/耗时差值当工具或Harness的因果效果。

运行revision `da2622bb88f39464d43f47097d432a32cbb22b69`；准备PR775三项CI通过，合科研分支`d5a226b04fd1650cbf635d55a6d91d4a3091c1dd`，二者代码内容一致。初次CI新增测试依赖服务器归档而缺文件，改隔离夹具后通过；该失败属于准备工程，不是模型实验。

用户授权新增1美元、确认起1小时，UTC08:14:16—09:14:16（北京时间16:14:16—17:14:16）。一次运行已结束，未达预算或时窗，无Provider/整次运行自动重试，不因余额追加尝试。Agent下载命令保留其生成的`curl --retry 2`，本次下载日志未观察到重试；不把任务内正常恢复当作重跑实验。

## 实际执行轨迹

1. 初始3请求读取作者构建说明，输出`./autogen.sh`→`./configure --disable-docs`→`make -j2`，没有预写依赖安装。真实autogen退出1，未展开`LT_SYS_SYMBOL_USCORE`。
2. 恢复检查libtoolize/autoreconf版本，搜索已安装宏与项目中的缺失名称；误把`libtool.m4`当包名调用package_files，得到未安装反馈，再正确查询libtool的安装文件。
3. 实际文件提供者查询`libtool.m4`成功返回系统libtool等候选，证明新工具在真实Agent过程中可用。但Agent查询的是它已知的宏集合文件，没有定位到真正提供目标宏的`ltdl.m4`。
4. 继续搜索USCORE、sys_symbol_underscore、SYS_SYMBOL等相近文本，合计16次诊断工具尝试，12次实际执行，最后4次因交接查询预算耗尽返回budget_exhausted。没有调用package_search或package_description；不是描述检索工具返回无结果。
5. Agent据有限已安装宏范围推断“2.4.7不再提供宏”，决定下载、配置、构建并安装真实Libtool 2.4.6到`/workspace/dependencies/libtool`。随后设置ACLOCAL_PATH/PATH，重跑作者autogen/configure/default make。
6. Workflow执行修订与生成物重置，主构建通过，交付静态库及真实共享库，随后在新容器从原归档重建并清理。真实依赖前缀的`share/aclocal/ltdl.m4:756`含`AC_DEFUN([LT_SYS_SYMBOL_USCORE],`；没有使用前轮Agent固定值兼容宏。

186个新增文件属于生成输出，当前source_review仍记pending_review；本次没有批准方案进入成功经验库，也没有改旧source_review或E57。

## 能说明什么，下一步是什么

上一轮工程验证已证明包描述检索能找到系统开发包，本次补充了自主Agent的实际选择：工具可用不等于Agent会优先使用它。它确实用了文件提供者工具，但仍把大部分诊断额度花在已安装宏的重复搜索上。单纯增加工具和索引，没有解决这个案例的提供者识别问题。

本次构建选择了真实工具链依赖，避免固定检测宏，属于有效构建路径；它比直接安装系统开发包增加了一套依赖源码构建。较前一独立观察请求31→10、费用与耗时更低，但两次初始方案不同且镜像变化，只有描述性意义，不据此声称工具带来确定降本或泛化。

下一候选应聚焦诊断动作顺序：已安装范围无定义后尽早查组件相关包描述，再核实开发包和文件提供者；重复同类宏搜索不应消耗全部额度。先交用户审核，暂不增加查询预算、自动实现新提示或追加付费尝试。当前主线仍是状态感知执行与轨迹驱动Harness改进；本单例可为后续提案提供材料，不替代系统比较。

## 证据

- [完整派生分析](../../benchmarks/analyses/libffi-index-autonomous-2026-11-16/README.md)、逐响应费用、12真实查询、清理及封存指针。
- 原件：`/home/yiwei/.codex/outputs/forge-libffi-index-autonomous-flash-2026-11-16-v1`；2408普通文件、20链接，inventory `3a43fdf2c10ca15a92ced38f15966b5ddc35ada07101edb8436abb203f574f0f`。
- 授权/准备发布/运行日志：`/home/yiwei/.codex/outputs/forge-libffi-index-autonomous-session-2026-11-16-v1`。
- 原报告：[依赖提供者与索引修复](2026-11-16-dependency-provider-repair.md)、[当前平台功能对照](2026-11-16-libffi-functional-comparison.md)。旧结果不改，不新增独立项目分母。
