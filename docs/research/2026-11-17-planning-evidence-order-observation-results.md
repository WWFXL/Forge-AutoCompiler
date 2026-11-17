# P5按证据顺序规划的三系统真实观察结果

身份：`cpp-build-planning-evidence-order-observation-flash-v1`；Issue #830。阶段：真实数据采集与结果分析。用户已审核P5并授权新增2美元/2小时；本批完成，不追加请求或补槽，结果待用户审核，未修改论文。

## 结果与解释

libuv、quickjs、libunwind各一次，3/3主构建、主要产物交付和干净重建通过，全部无需恢复Agent，原输入文件未改。17次请求全部为初始规划；保守估费0.0983376美元，整批334.34秒（约5.6分钟）。结果说明已审核P5能够驱动三个构建系统的完整执行；单组、已知项目观察不能证明其比P0更省或完成率更高。

| 项目 | 构建系统/采用入口 | 主构建及干净重建 | 规划/恢复请求 | 规划秒 | 总秒（含重建清理） | 估费美元 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| libuv | CMake | 通过 | 3/0 | 7.34 | 80.46 | 0.0135390 |
| quickjs | Make | 通过 | 4/0 | 8.65 | 91.46 | 0.0157272 |
| libunwind | Autotools（仓库另有其他入口） | 通过 | 10/0 | 26.79 | 161.35 | 0.0690714 |

同槽无已知成功指令复用、无动态经验检索、无本项目答案注入。P5仅追加初始规划指导，当前LH_v1的恢复提示、工具、诊断记忆、上下文容量、Workflow和独立验收保持。模型统一deepseek-flash thinking low，17份响应身份符合，无自动重试、不补槽，0未知用量、0未启动。输出方案均完整，未触发结构纠正；不能因此声称dsvpn/zstd输出根因已解决。

## 规划路径具体发生了什么

### libuv：说明与脚本先行，但工具参数误用增加一轮

初始材料已经含README、CMakeLists.txt和configure.ac。Agent补读CMakeLists.txt的200行以后片段，再查询cmake/gcc版本，随后提交`cmake -B build`、`cmake --build build --parallel 2`。依赖由系统现有工具满足，无安装步骤。

首次环境查询传入`cmake --version`、`gcc --version`，而该工具要求query为工具名；两次返回invalid_query。Agent随后改成`cmake`、`gcc`查询成功，再交付完整方案。因此3次请求中有一轮用于自行纠正工具参数，并非项目缺依赖或Workflow误判。记录保留，不在本批修改工具后重跑。

### quickjs：直接使用Make入口，补查实际目录和默认构建内容

初始材料含Makefile及两个readme。Agent列出根目录，补读Makefile的379行及498行以后片段，并查看intl、temporal目录，核实gcc/make可用，提交`make -j2`，未虚构configure阶段。4次规划请求，无恢复。

这些目录检查有构建文件背景，不能一概称无意义。它同时说明提示词的“定向补查”允许具体疑点驱动的额外读取，并不是强制只读两份文件。

### libunwind：可执行方案正确，调查仍偏长

初始材料包含README、configure.ac以及其他构建入口。Agent读取configure.ac的160、279、398、517、636、754行起片段，读取Makefile.am，查看src/m4/config目录，并查询autoreconf、libtoolize、automake、make、gcc、g++、pkg-config及相关开发包。合计10次环境查询，10次规划请求，无恢复。

最终说明仓库README同时保留Autotools说明；据实际脚本安排`mkdir -p m4 config && autoreconf -i`、`./configure --prefix=/usr/local`、`make -j2`，顺利完成。规划中确认zlib/lzma为可选探测能力，且现有环境已装，不额外安装。

本槽没有完全相同参数的重复read_source，但对configure.ac连续补读较多，说明“没有重复读取”不等于“已最小化探索”。目前能确认调查有实际脚本和环境证据，尚不能认定每一项都有必要，或认定P5已实现理想收敛。其费用占本批约70.2%，后续比较应同时观察前期调查与恢复节省。

## 可以与不能得出的结论

本轮新增了P5真实提示送达、三类构建入口生成、从零执行与重建的端到端证据；三槽均无相同参数的read_source重复调用，已有说明直接进入初始材料，没有为满足顺序机械重读README。工具反馈能够被用于纠正参数后继续提交。

这只是三个已开发暴露项目的一次单组观察，没有同时运行P0；不能把与E60的请求差值解释为P5因果收益，也不将3/3提升为新的总体成功率。全部环境满足所需依赖，本批没有检验发现缺包并生成安装指令的能力；恢复0也不验证恢复质量。建议保留P5作为已可运行候选，下一步在新的项目集、同一当前LH_v1底座上进行P0/P5公平比较，不先增加CCScanner或叠加提示修改。

## 核对与原始证据

授权保守时窗UTC2026-11-17 15:44:40—17:44:40（北京时间11月17日23:44:40至18日01:44:40）；运行已提交版本254dfd1f，期间仅更新状态与派生分析，不改固定运行组件。manifest SHA-256：`a6c5322feb0f4bc57f0963a7b2bec940af23bae16371f87fab2b2a02b7a04e3e`，P5候选568429c4保持。

逐响应输入305680、输出5528，共311208 Token；按协议输入/输出每百万0.30/1.20美元、输入均按非缓存价格保守复算，与三槽账本总额0.0983376美元一致。这是协议估费，不是Provider账单。3槽cleanup通过，12个容器名称/ID引用实查均不存在。源码后审确认三槽均无原有文件修改，新增为构建生成文件及产物；独立后审记录不修改原pending_review状态。

正式进程退出0，seal后只读核对通过：12702文件、44符号链接，inventory `2bbec0c48e65ad0d7f8270023b4202e1cd6a3d6cbf554a627200bcd0da20c220`。所有失败/纠正和全部开销保留；无活动模型任务，本批余额不扩用于其他实验。

- 原件：`/home/yiwei/.codex/outputs/forge-planning-evidence-order-observation-flash-2026-11-17-v1`。
- [完整动作轨迹、分项和复算程序](../../benchmarks/analyses/planning-evidence-order-observation-2026-11-17/README.md)。
- [固定协议](../../benchmarks/preregistrations/cpp-build-planning-evidence-order-observation-flash-v1.md)。
- [用户审核的完整P5提示差异](2026-11-17-planning-evidence-order-proposal.md)。
