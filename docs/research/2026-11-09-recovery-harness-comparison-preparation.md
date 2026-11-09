# 同初始方案的恢复Harness比较：实现与准备

Issue #711；用户已审核[高级模型实际提案及完整提示差异](2026-11-09-recovery-harness-proposal.md)，并要求开始比较实现。本轮完成必要基础设施和零费用真实构建，消除同初始方案、费用归属及新项目任务装配的阻塞。**真实比较0/36、Provider调用0、论文未改。** 实现验证不能证明R1有效。

## 公平比较如何执行

每项目先让Flash按H0提示只读源码并规划一次，保存完整初始方案及其哈希。随后H0与R1在各自全新容器中执行完全相同的初始方案，真实失败才进入恢复；同一模型、工具、状态路由、Workflow、资源和独立检查。R1仅追加已审核的1677字节恢复指导，SHA35280b6a11f01ef5da56d438659f0492c12ea8a82c18ac3d8a3b2e0e89d14ecf，不改变初始规划。不会把第一组的恢复轨迹或修订送给第二组。

18项目各方法一次、共36执行槽；三系统交错，H0/R1先执行各9次。初始规划共有18个任务，规划请求可能多于18次，全部计费。某共同规划失败时，两执行槽记未启动/共同规划阻塞，不制造两次恢复失败，不重新规划补槽。没有自然失败的项目不支持恢复策略增量结论。

实际批次费用将共同规划计一次；独立部署比较时，两方法各自承担该共同规划全额费用和时间。初始失败、格式纠正及恢复全部计入。R1此前提案0.105856美元单列，含提案部署费用另报；历史来源投入不再支付，也不冒称完整生命周期费用已经核清。未知用量时只报告已知支出，总费用留空。

## 新项目、目标和作者依据

沿PR710公布的18候选，完整固定仓库/源码commit，全部采集成功，未按方法成绩替换。公开目标统一为main-build-v1：作者推荐或默认方式构建主要程序/库，保护原源码/测试，不额外安排Debug、静态、全部示例或完整作者测试。

| 系统 | 项目 |
| --- | --- |
| CMake | cglm、tini、wasm3、libhv、ggmorse、DuckX |
| Make | massdns、redsocks、beanstalkd、no-more-secrets、berkeley-softfloat-3、Turbo-Base64 |
| Autotools | libmodbus、freesasa、fsarchiver、fastq-tools、munge、twemproxy |

[作者定义](../../benchmarks/fixtures/recovery-harness-comparison-v1/definitions.json)保存主要组件声明、原文引用/行号和独立参考动作，[任务装配](../../benchmarks/fixtures/recovery-harness-comparison-v1/tasks.json)保存35个主要组件、原文件SHA、公开任务及私有检查。主要组件按作者语义登记：fastq-tools九个程序、munge主库及五个程序保留；no-more-secrets的sneakers在作者README明确可选，普通目标只要求nms。softfloat使用作者嵌套Make目录。

三个作者原生轻量验证通过数据登记，不改Workflow项目规则：redsocks -v、nms -v、fsarchiver -V，使用源码中的真实输出依据；其余沿共同默认验证。完整作者测试为not_required。独立参考动作、主要产物名单和这些验证要求不送入规划Agent。

镜像固定sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a，构建/重放并行2。只有三个项目进行了独立参考实建；其余已读作者声明并装配任务，尚不能声称18项都已验证可构建。三篇论文的名称池/官方数据包差异、开发暴露边界沿PR710报告披露；这些不是最终holdout。

## 实际实现验证

五条零Provider容器路径完成主构建、独立主要产物、精确交付、最终轻量验证、干净重放、源码保持及清理：

- 作者普通路径：cglm/CMake、massdns/Make、libmodbus/Autotools，各一次。
- massdns受控错误target→一次脚本Agent修订→Workflow继续：H0和R1各一次，初始方案哈希相同。实际请求中只有R1含新增指导，初始提示保持H0。

五条累计101.14秒；两次脚本响应/0Token/0真实Provider/0费用，20个容器名称/ID核对均不存在。脚本响应不是Flash效果，不计自然失败频率或R1恢复成功率。17相关检查覆盖共同方案隔离、费用一次支付/部署两侧全额、失败/未知用量/清理/模型异常停止、未启动分母及实际H0规划图；修改文件Ruff/格式通过。CI和发布终态以关联PR/GitHub为准。

准备中的首次来源schema检查发现轻量验证缺少输出依据并在任务提交前补齐；未产生Provider请求。首次实跑v1在cglm完成后因汇总字典重复method字段中止，原cglm结果及失败保留；修正驱动汇总后v2独立完成五条，不续跑或改写v1。v2之后只扩充分析汇总，不改变已验证执行分支。工程过程不计方法效果。

## 入口及下一步

[比较入口](../../scripts/forge_recovery_harness_comparison.py)提供prepare/check/run/analyze和独立零费用verify-runtime，[来源入口](../../scripts/forge_recovery_harness_sources.py)提供collect/freeze。[预注册](../../benchmarks/preregistrations/cpp-build-recovery-harness-comparison-flash-v1.md)和[manifest](../../benchmarks/manifests/cpp-build-recovery-harness-comparison-flash-v1.json)固定范围。

```bash
python scripts/forge_recovery_harness_comparison.py --check-prepared
python scripts/forge_recovery_harness_comparison.py --run --authorization /absolute/path/authorization.json --output /absolute/path/new-evidence
python scripts/forge_recovery_harness_comparison.py --analyze /absolute/path/new-evidence
```

运行需已安装backend依赖及可达Docker；CLI准备不读取凭据。建议正式新增硬上限5美元、确认起4小时；授权须绑定当前manifest SHA和用户答复。此前一次提案1美元/时窗不续用；正式调用只有Flash，无新RichLab提炼/Jev。无自动重试、不补槽，未知用量/模型身份异常/清理失败停止。结果先汇报审核，用户同意后才写论文。

## 原件位置

- 来源：/home/yiwei/.codex/outputs/forge-recovery-harness-sources-2026-11-09-v1；18个固定commit源码包、普通文件索引及原文。
- 工程v1/v2：/home/yiwei/.codex/outputs/forge-recovery-harness-engineering-2026-11-09-v1、同名v2；真实命令/请求/响应、交付、重放和失败均保留。
- 会话：/home/yiwei/.codex/outputs/forge-recovery-harness-comparison-session-2026-11-09-v1；验证、发布和知识库收据。
- 尚无本身份正式比较原件；E51/E52和论文v0.10均保持。
