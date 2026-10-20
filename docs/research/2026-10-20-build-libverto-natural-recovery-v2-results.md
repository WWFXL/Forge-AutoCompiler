# libverto 同源最小配置修订资格 v2：修订后仍失败

Issue #530 / PR #531；独立身份 `cpp-build-libverto-natural-recovery-v2`，协议/实际运行 release `3f9b143b46b7197f5c4b52167cc7fc167e4e9bd1`。用户本轮继续指令下的新零模型时窗，单槽一次；旧 #504/#524/v1/raw 不修改、不续跑。显式使用 #526 planner v2，依赖单命令600秒、节点1200秒、evaluator/replay各900秒、cleanup120秒，03:30 UTC截止，完整任务不变。

## 实际观察

| 顺序 | 动作 | 结果 |
| --- | --- | --- |
| 1 | 原始依赖安装 | 成功，63.77秒；此次到达目标状态 |
| 2 | 原 autoreconf、静态-only configure、make -j2 | 全部退出0 |
| 3 | 原 make check | 六项全部失败，TOTAL6/PASS0/FAIL6，六个上下文创建断言 |
| 4 | 唯一修订 | configure 改为 `./configure --enable-shared --enable-static`，其余命令与固定任务不变 |
| 5 | 新 configure、原 make -j2 | 均退出0；configure确认共享/静态均启用，make耗时0.17秒并报告 Nothing to be done |
| 6 | 新 make check | 再次TOTAL6/PASS0/FAIL6，同六上下文断言 |
| 7 | 停止与清理 | 第二次失败触发交接，但不允许第二次修订；PlanContractError停止，实际容器已删除 |

最终 strict completed=false；8条Shell、一次实际修订/revision2、两个失败交接，0模型请求/Token/费用/未知用量。精确交付与clean replay未执行，记为未观察，不能记通过或失败。所有原有源码普通文件保持原hash。

权威阶段记录正确保留dep/autoreconf两条前缀，旧configure/build完成记录失效且实际再次执行。但文件系统中旧构建产物仍存在，增量make没有重新编译/链接，测试可执行物也均up-to-date。这揭示了“逻辑完成记录失效”与“实际构建缓存/产物失效”的区别。当前只证明所冻结的单项修订不足以恢复；清理重建是否足够仍是未验证候选，不从日志推断最终根因已经穷尽，也不因此否定整个方案Workflow主线。

## 证据与核验

- Raw：`/home/yiwei/.codex/outputs/forge-libverto-natural-recovery-v2/`；236普通文件/4链接/7762235 bytes。
- Inventory canonical SHA-256：`c02679e3e789e4d17f9d0d737f84457c868d4dd31399d1e9120bde85110aba29`，73组件全部快照封存。
- 独立stdlib实现：`/home/yiwei/.codex/outputs/forge-research-continuation-2026-10-20/audit_libverto_v2.py`；输出同目录 `libverto-v2-independent.json`，valid=true、issues=[]。
- 核验完整typed inventory、组件hash、全部命令日志、原0/6/修订后0/6、单项方案差异、前缀保留与后缀失效、原源码、零模型事件和Docker实际cleanup。没有重跑旧实验。首次审计误以为Session命令直接含log_sha256，修正为核对inventory，初版脚本保留；不影响raw或结果。
- 新入口/诊断/修订13项回归与Ruff/format通过。发布必须在最终head三项实际CI全SUCCESS之后，合入依赖分支，未进main。

## 下一决定

按一次修订边界封存本例，不通过删除失败、改测试或追加修订挽救。下一阶段冻结前瞻角色/项目族暴露登记的完整三策略比较，保留强工具接口、合理规则和失败Agent，计入所有初始规划/读取/输出/失败/恢复费用；小幅收益或明确取舍可继续研究，不要求所有指标胜出。RQ3固定完整分母，区分build成功、有效测试、交付、干净重放和未观察。新Provider预算与时窗需在调用前明确，旧夜间$20授权已截止，本例新增支出为0。
