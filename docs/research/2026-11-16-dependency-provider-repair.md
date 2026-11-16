# 依赖提供者与软件包索引诊断修复

2026-11-16，Issue #772；工程修复与零Provider真实构建，不新增模型效果实验。

## 修复了什么

过去的`package_search`只搜索包名，无法通过“libtool”发现描述中关联它的`libltdl-dev`。原编译镜像还清空了APT列表、没有apt-file：本地搜索只能看到有限的已安装包，文件提供者查询实际上不可用。问题不只是Agent推理，也包含工具能否提供所需证据。

本轮将搜索扩展为包名及描述，增加精确`package_description`与只读`package_index`。APT查询返回Packages/Contents存在性、apt-file可用性及覆盖说明；区分没有索引、查询不可用、当前索引内无匹配，不把空结果等同不存在或新版移除。文件查询按完整文件名或路径后缀匹配，不能拿宏名当文件名搜索；实际文件内容搜索仍查已安装目录。

恢复提示引导“缺失项→提供文件/组件→开发包→安装/路径”，没有加入libffi专用答案。查询不自动联网、安装或推进阶段；准备和修复由Agent提交dependency动作，再交Workflow执行。文件索引扫描首次触发旧8秒时限，最终只将该类查询调整到内部20秒/外部25秒，继续受每交接12次和任务剩余预算约束；其他查询保持8/15秒。

## 镜像与真实查询

新镜像通过[Dockerfile](../../docker/compile/Dockerfile.dependency-index)从已核验的`autocompiler:gcc13-https-v1`构建，新增apt-file 3.3、libapt-pkg-perl、libregexp-assemble-perl三包，无包删除，没有安装libltdl-dev。Packages索引15份、Contents索引4份。不可变ID：

`sha256:d483ffa7b71b9545cff9555f6c92b6281a3f826ce006e2d09134cbdca92f8aa1`

旧镜像及冻结实验不变；未替换全局默认。后续比较应给各方法统一新镜像，并独立说明索引预备成本；环境变化不能作为某个Harness的收益。索引只覆盖当时配置源和架构，不保证始终最新。

| 实际查询 | 观察 |
|---|---|
| 原镜像索引 | Packages/Contents均0，apt-file不可用 |
| 原镜像libtool搜索 | 只有有限已安装缓存，缺失目标开发包 |
| 新镜像libtool包名及描述搜索 | 返回libltdl-dev及其GNU libtool描述 |
| 新镜像精确包描述 | 包版本2.4.7-7build1、Source为libtool |
| 新镜像ltdl.m4文件查询 | libltdl-dev: /usr/share/aclocal/ltdl.m4 |
| 独立头文件/usr/include/zlib.h | zlib1g-dev: /usr/include/zlib.h |
| 不存在文件 | no_match_in_index；apt-file退出1 |

apt-file实现中的返回常量已实际核实：无结果1，通用错误2，空缓存3，无匹配索引4。仅输入`zlib.h`会返回大量Linux内核同名头并触发8KB截断，明确保留`truncated`；补充完整路径查询得到单一开发包，不把截断当没有结果。

## 一次端到端工程验证

[预定边界](../../benchmarks/preregistrations/cpp-build-dependency-provider-repair-v2.md)，[入口](../../scripts/forge_dependency_provider_repair.py)：固定原libffi归档与公开主库目标，仅将镜像替换为新不可变ID并重绑参考摘要。原历史初始方案实际缺宏，脚本回复通过真实Agent工具链进行项目文本、索引、包名描述、精确描述、文件提供者及未安装状态六次查询，再提交预写补包方案。

主库构建、静态/共享交付、原归档干净重建及cleanup均通过，82.38秒；原输入内容/权限未变，正常生成文件变化保持后验审查记录。7次脚本回复、6次工具查询，0真实Provider、0Token、0美元。诊断命令未进入成功配方；主构建和replay的四个名称/ID实查均不存在。

这一观察证明查询接线可用、真实开发包修复可以完成任务。它没有让Flash自主选择下一动作，不证明Agent会找到依赖或节约费用。上一轮Agent当前平台构建成功的结论保持，本轮改进的是诊断证据与路径选择条件，不追改旧结果或论文。

## 检查与下一步

20项相关测试、Ruff与格式检查通过；测试退出时旧pytest目录权限清理告警保留，不是本轮构建容器清理失败。首次镜像构建误用裸SHA作为FROM，被当远程仓库解析而403，未执行RUN；v1失败完整保留，v2使用本地已核验tag。初次8秒查询超时同样保留。

修复阶段到此结束。下一项宜做一条不提供包名/既往方案的自主构建观察，检查Agent是否实际使用描述与提供者查询，再决定是否在更多新项目比较。若使用新镜像，需明确它与历史结果的环境差异；新的Provider调用另绑定预算及时窗。

## 证据位置

- [派生摘要与查询](../../benchmarks/analyses/dependency-provider-repair-2026-11-16/README.md)。
- 原件：`/home/yiwei/.codex/outputs/forge-dependency-provider-repair-2026-11-16-v2`，含镜像日志、包差异、初次/最终容器查询、完整Workflow/模型脚本交互、命令、交付/重建、清理与运行快照。
- inventory：`e5141d035caf6a0271378b5600237a9399e568fe8ea3d6dfed3cb8649f518832`，1354普通文件、8链接。
- 首次镜像失败原件：同前缀`v1`。不覆盖旧工程或正式实验。
