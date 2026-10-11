# Jev 自然失败 build qualification v2 设计

日期：2026-10-11。追踪：Issue #413。父证据：
`cpp-jev-natural-failure-source-catalog-v2`，报告 SHA-256
`5ac8824a17bbc72307c39df0f0605284a03897f0149bfc9ecca9b7aab13887f8`。

## 1. 研究问题

source catalog 已为 CMake、Make、Autotools 各冻结 8 个未见项目族和 exact commit，但没有执行构建。
本阶段回答：

> 在相同 Forge 镜像、标准根入口和禁网环境中，这 24 个固定项目能否形成跨构建系统、双 clean run
> 一致、且排除网络、平台、超时和基础设施原因的自然 configure/build 失败？

这是零 Provider 数据资格实验。它不评价 Jev 或 Agent，也不建立 reference recipe 或动作矩阵。

## 2. 冻结样本与角色

任务集合逐字读取 catalog 报告 `qualification.projects`。报告已经固定 project family、repository URL、
exact commit、构建系统、system rank 和 design/calibration/evaluation 角色。build runner 校验父报告哈希、
`8/8/8` 配额、24 个唯一 family 和 catalog 决定后才能执行。

任何项目 clone、构建成功、失败、超时或不合格后均不得 replacement、backfill、前移角色或切换构建系统。

## 3. 环境与标准路径

- 镜像：`autocompiler:gcc13@sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`；
- host 以 `git init`、`git fetch --depth 1 origin <exact SHA>` 和 detached checkout 取得源码；
- catalog 已排除 `.gitmodules`，checkout 后再次核验，出现时按 source drift 排除；
- 每个 replicate 复制一份全新源码树和空构建状态；
- Docker 使用 `--network none`、4 jobs、宿主 UID/GID；
- CMake：`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`，成功后
  `cmake --build build --parallel 4`；
- Make：`make -j4`；
- Autotools：依次选择 `./autogen.sh`、`./bootstrap` 或 `autoreconf -fi`，随后 `./configure`、
  `make -j4`。

每项目两个 replicate；clone/fetch/checkout 和单构建命令各 180 秒，单 replicate 300 秒，总 attempt
14400 秒，无重试。

## 4. 结果分类顺序

完整 stdout/stderr 保存后按以下优先级分类：

1. Docker 客户端/daemon 错误为 `infrastructure_failure`；
2. 命令或 session 超时为 `timeout`；
3. DNS、连接、代理、下载或远端 clone 错误为 `network_dependency_failure`；
4. 日志明确声明只支持 Windows/macOS、拒绝 Linux 或要求另一 OS 时为 `platform_incompatible`；
5. 其余非零退出为 `bounded_failure`，并规范化为 configure required、missing dependency、missing tool、
   incompatible toolchain、target/layout、compile error 或 unknown；
6. 标准路径完整退出 0 为 `initial_success`。

只有两个 replicate 都是 `bounded_failure`，且失败阶段和规范化类别完全一致，项目才是
`stable_natural_failure`。网络失败即使两次完全一致也必须排除。

## 5. 故障隔离

正式运行前测试注入 clone、fetch、checkout、Docker command 和 cleanup 超时/错误，并证明：

- 每个故障写成项目级 observation；
- 后续项目继续执行；
- 已完成项目和完整日志不会因后续错误丢失；
- timeout 后按 experiment label 对账并清理容器；
- 单项目异常不能把整个 attempt 提升为 `attempt_failed`。

只有协议漂移、父报告漂移、create-once 冲突、搜索样本数量漂移或总 attempt 硬预算耗尽属于全局失败。

## 6. 资格门槛

`stable_natural_failure` 必须同时满足：

- CMake、Make、Autotools 的 design 各至少 1 项；
- 三个系统的 calibration 各至少 1 项；
- 三个系统的 evaluation 各至少 2 项；
- 两次 replicate 的阶段和类别一致；
- 0 cleanup failure，结束后 0 受管容器；
- 0 credential read、0 Provider request、0 model token。

全部通过时决定为 `proceed_to_reference_recipe_qualification_v2`；否则决定为
`stop_natural_failure_build_qualification_v2`。唯一 attempt 完成后不得重跑或修改标签。

## 7. 结论边界

通过只说明固定 24 项中存在足够的稳定自然失败来源，允许另行审核可成功的 reference recipe。它不证明
这些失败存在安全直接动作、不证明 RuleGate 未饱和，也不授权 Jev/Agent 比较。

失败只否定当前 GitHub 搜索快照、Linux 镜像、标准入口和角色冻结组合。若失败原因主要是平台项目或根
Makefile 不是 Linux C/C++ primary path，则结论应指向 source contract 仍不足，不能解释为 Jev 无效。

