# 配置状态增强实现与下一项配对实验

Issue631；方法实现与实验准备。目标是在已有模型规划＋Workflow＋失败Agent基础上，让显式任务要求参与执行中的状态判断与动作选择。当前没有新增真实Provider结果，不能把以下开发检查写成论文方法效果。

## 方法增量

`goal_state.py`从原公开固定任务静态读取requirements字面布尔字典及原默认静态库要求，保存任务脚本SHA；不执行任意Python、不读取历史正确配方或个人知识库。目标在初始规划、恢复和Workflow中持续保留。

最后一次configure成功后、第一次build前，读取实际生成的CMakeCache：每项记录目标值、实际值、类型、文件SHA、命令前沿和方案版本。观测时原缓存按内容保存在Session的`logs/goal-state/`，后续重新配置不能抹去原依据。匹配为satisfied，明确冲突为violated，缺缓存/缺变量为unknown；没有可解释目标时保持unknown并沿原流程执行。

动作选择是有界的：同根项目、同缓存、实际BOOL值、原作者option/cmake_dependent_option或CTest开关声明均有证据时，最多一次追加configure修订，作为正式命令进入审计和clean replay。编译后缀失效，原配置记录保留。不存在目标开关声明、HAVE_*依赖探测、缺证据或复杂配置仍交原Agent；不强设“依赖已找到”。方案变化后旧状态失效并重新观察，避免旧配置错误覆盖新命令的真实失败原因。

这是一项自动化编译领域的方法组合候选：显式目标、执行观测及动作选择。当前没有学习分类器、自然语言依赖理解或新通用算法的主张。现版只支持CMake任务中上述显式配置形式；Make/Autotools继续使用原执行/最终验收，后续根据数据再扩展。

## 实际检查

最终24项相关检查通过，包括任务目标与哈希、未知证据、源码内路径、依赖探测不可强设、真实状态到动作、修订后的状态失效、原源码准备及时间/宿主边界。Ruff check/format通过；没有重复本地全量产品测试。

其中一项显式启用真实Docker：原受控CMake夹具初始BUILD_TESTS=OFF，configure退出0后立即识别目标偏离；选择器追加一次BUILD_TESTS=ON的配置命令，仅执行一次build，原测试/静态库精确交付/同镜像干净重建/字节比较和cleanup完整通过，模型请求、Token与Provider费用均0。它是受控开发检查，初始错误和规划均为脚本，不代表真实模型恢复或自然任务成功率。

本轮检查产物位于`/home/yiwei/.codex/outputs/forge-goal-state-session-2026-10-27/final-checks/`；此前开发夹具在同会话`docker-check-1/`保留。最终测试入口为`backend/tests/test_goal_state_docker.py`，需显式设置`FORGE_RUN_GOAL_STATE_DOCKER=1`。没有创建本24槽正式attempt或写入其正式结果。

旧324个父实验组件逐文件SHA保持，不改旧raw、manifest、结果布尔或未观察分母。默认产品Lead入口不变，本次增强接入独立科研执行入口。

## 已准备的真实实验

`cpp-build-goal-state-paired-flash-v1`：六个已有任务check/simdutf/snappy/yaml-cpp/libtommath/tinyxml2，各两次新鲜重复，当前模型Workflow/增强版各一次，共24槽；每对交替顺序，详见同名manifest和preregistration。全部已见，simdutf是开发动机案例，不能据此推未见泛化。

统一deepseek-flash thinking low、原2CPU/root/依赖网络/任务/固定原测试/源码保持/精确交付/完整replay。目标呈现和观察带来的全部模型及执行开销计入。主要报告完整完成、费用、耗时，辅助记录配置发现阶段、直接修订/Agent恢复和编译次数；失败与时窗截断分开，不把false都当能力失败。

时间条件统一为node1200、完整replay1200、清理余量300秒，新槽至少剩2700秒；请求准入保持600秒。外层预留覆盖内部链，避免本轮CXX参考的900秒外层与1500秒内部不一致问题。运行在新的完整有效时窗前段开始。

候选设计费用最多10美元，尚不代表用户授权；旧授权UTC12:44:30已结束。正式运行需新的用户预算与起止时间，以及绑定候选SHA的authorization.json。所有失败保留，无自动重试；未知用量、身份异常或实际cleanup失败停止整批，不续旧身份、不补槽。

准备和检查均无需凭据：

```bash
cd backend
PYTHONPATH=. uv run python ../scripts/forge_build_goal_state_comparison.py --check-prepared
```

授权后复用已有计量/资源/封存接口运行，最终用`--analyze <evidence-root>`生成派生表；无需再开展一轮完整资格构建。后续才进行增强版与CXXCrafter的新系统比较，旧参考不回填。
