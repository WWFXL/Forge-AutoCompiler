# libverto最小配置恢复资格：目标状态未观察

Issue #524，身份`cpp-build-libverto-natural-recovery-v1`，运行release`2e60734f`；这是后验已见自然失败的零模型单例资格，不是效果比较。原#504失败与全部成本不变。本次没有验证修复成功。

## 实际发生与未发生

固定原source/image/task和原libverto-r2-plan初始方案，单槽一次。第一个依赖命令`apt-get update`后安装开发依赖，在60.117秒触及冻结60秒单命令上限，exit124/timed_out=true。日志显示正在下载约6481kB依赖，没有完成该动作。

Workflow据此对dep步骤生成一次handoff，revision仍1、completed空。未进入autoreconf、configure、build或make check；预定六断言失败未复现，修订函数未执行、plan2不存在、0 replay。不能把0/6旧结果填到本次，也不能将此停止当作最小配置修订无效。

包装层`planner_for`在判断handoff是否为check前直接读取`tests/test-suite.log`和config.log；由于依赖阶段停止，这些文件不存在，表层记录为FileNotFoundError。直接初始停止原因由权威命令/Workflow日志确认为依赖超时；两件事必须分开记录。后续新身份需要先检查交接阶段，再读取专属诊断文件，并加入早期失败回归；现冻结脚本/协议和raw不修改、不重试。

Session failed、strict completed=false，cleanup成功且实际容器已移除，原源码文件与精确归档相同。0凭据/模型请求/Token/Provider/未知用量，唯一执行命令为依赖动作；没有模型事件或请求/响应文件。首次独立审计误以为零调用也总有events.jsonl而停止，脚本保留，v2独立审计按允许空事件并验证无请求/响应文件完成；未改raw。

## 封存与验证

raw `/home/yiwei/.codex/outputs/forge-libverto-natural-recovery-v1/`，122普通文件/0链接/2062872 bytes，inventory `e0f674f48fccecadf500fb17fb05a70b16a1e4303a91be594fe0a38974d30363`。manifest为`benchmarks/analyses/cpp-build-libverto-natural-recovery-v1.json`，68组件；独立审计`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/libverto-natural-recovery-v1-independent.json` valid=true、issues=[]，核验全部inventory/组件、原方案/父指针、唯一命令/未观察状态、0调用、原源码与实际资源清理。

7项针对性测试/Ruff/format通过；测试覆盖修订函数的前提和单项变更，但没有覆盖包装层早期dep交接，实际运行暴露了这一遗漏。不能用测试通过替代真实资格成功。最终结果head三项实际CI全SUCCESS后才合并，失败原样发布。

## 决定

本身份封口，不因失败放宽完整六测试、改源码或补跑。#522日志/源码解释仍成立，最小配置修复的端到端反事实仍未知。60秒安装上限在本次未能支持原依赖方案；将来用新身份前先根据已知依赖耗时设计足够资源和准入保留，预算变化提前冻结，不与父结果作因果比较。

下一步具体入口：先补包装层交接阶段检查和无测试日志的失败回归；在新的有效执行时窗下冻结原坏方案与最小configure修订资格，再看完整六测试/精确交付/replay。不是直接追加模型、复杂选择器或论文写作。UTC22:35后本资格不准入新槽位，22:45后本轮仅清理交接，23:00绝对停止；共享已知模型估算仍$5.80615200，另未知预留$1，预算占用$6.80615200。
