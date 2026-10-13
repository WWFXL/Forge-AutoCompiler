# cpp-progress-aware-replay-closure-qualification-v1

## 身份与目的

- Tracking Issue：#442
- 类型：零 Provider 工程机制资格
- 目的：验证 H2 replay-closure 状态能否在候选冻结前识别已知 recipe 闭包缺口，同时不误拦三种构建系统的正确 recipe。
- 结果不得解释为 H2 相对 H0/H1 的成功率、成本或 token 效应。

## 固定案例

负例：

1. Make recipe 成功构建依赖工作区中较早生成、但未列入 recipe 的源文件；预期 `missing_generated_input`。
2. Autotools 冻结源码只有 `configure.ac`，工作区已有较早生成的 `configure`，recipe 直接执行 `./configure`；预期 `missing_bootstrap_step`。

正例：

3. CMake 完整 configure/build/stage recipe；预期通过。
4. Make 完整 build/stage recipe；预期通过。
5. Autotools 包含 bootstrap/configure/build/stage 的完整 recipe；预期通过。

案例使用通用本地夹具和冻结 source archive，不依赖项目名分支，不读取 v3 arm 的未冻结工作区。

## 主要门槛

- `5/5` 案例按预期有界终结；
- `2/2` 负例在 candidate freeze 前被拒绝，分类精确匹配；
- `3/3` 正例通过 preflight；
- `0` preflight 写入正式 replay attempt，`0` Session 进入终态；
- frontier 变化后旧 pass 不可复用；
- `5/5` cleanup 成功，结束后受管 preflight/replay container 为 `0`；
- credential read、Provider request、model token、formal effect attempt 均为 `0`。

## 停止规则

任何主要门槛失败即把本 identity 封口为失败，不重跑、不 replacement、不 backfill。测试或 runner 在 identity 创建前发现的工程错误可修复；identity 创建后的 observation 永久保留。

## 解释边界

通过只支持“机制能发现这两类已知 closure 缺口，并在三个最小正确夹具上不误拦”。它不支持对未见真实项目的召回率、跨项目泛化、Agent 修复能力、Provider 成本收益或论文主张作结论。下一阶段必须使用新 identity 和未见项目族。

