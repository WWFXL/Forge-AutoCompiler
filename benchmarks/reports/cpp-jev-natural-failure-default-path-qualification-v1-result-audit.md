# Jev 自然失败默认路径资格 v1 结果审计

日期：2026-10-12。追踪：Issue #419。被审计 identity：
`cpp-jev-natural-failure-default-path-qualification-v1`。

## 结论

停止在 reference closure 之前，决定为 `stop_before_reference_closure_qualification_v1`。

唯一正式 attempt 的机械决定是
`stop_natural_failure_build_reference_qualification_v1`。直接触发项是已知 Windows 项目
`gta-reversed` 在 target 尚未暴露时仍被保守分类为 `stable_failure_candidate`，违反了预注册的“已知非宿主项目
不得成为 failure candidate”门槛。

该门槛写得过严：v5 的核心合同原本就允许失败点之前没有 target 证据的项目保持 unresolved，并要求后续
reference recipe 用同一默认 target 的 Linux 用户态闭合将其排除。因此不能把这条机械失败解释为动态分类器已经
证明 `gta-reversed` 是宿主项目，也不能据此否定 reference-closure 机制。

但是不需要建立 replacement identity。固定 CMake calibration 三个槽的合格自然失败上限已经是 `0/1`：

| 槽 | 项目 | 正式默认路径结果 | reference 资格上界 |
| --- | --- | --- | --- |
| `cmake-04` | `kimwalisch/primesieve` | `stable_host_userland_closure` | 默认路径已经成功，不是自然失败 |
| `cmake-05` | `gta-reversed/gta-reversed` | `stable_failure_candidate` | v4 exact-commit 审计确认默认 endpoint 是 Windows DLL，不能用同一默认 target 闭合为 Linux 用户态产物 |
| `cmake-06` | `seL4/seL4` | `stable_non_host_target` | 动态证据确认是 kernel contract，不是 Linux 用户态终点 |

预注册要求 CMake calibration 至少 1 个 qualified natural failure，且禁止 replacement、backfill 和角色前移。
所以即使删除过严门槛，reference 阶段也不可能改变停止结论。本轮不创建 reference identity、typed-action matrix
或 Provider 三臂实验。

## 正式观察

- 36/36 个冻结项目完成，72/72 个 clean observation 保存；
- 23 个 `stable_failure_candidate`；
- 5 个 `stable_host_userland_closure`；
- 5 个 `stable_non_host_target`；
- 2 个 `stable_no_compiled_artifact`；
- 1 个 `network_dependency_excluded`；
- 0 infrastructure failure，cleanup 后 0 managed resource；
- 0 credential、0 Provider、0 model token；
- formal audit：273 files / 7,053,633 bytes，inventory canonical SHA-256
  `97b42a7ffb1c2da66fb2c4e38395d6410e246199344ffa03f2bac37a48bde09a`，`valid=true`。

三个系统的稳定失败候选按冻结角色计数为：

| 构建系统 | design | calibration | evaluation |
| --- | ---: | ---: | ---: |
| CMake | 2 | 1 | 3 |
| Make | 2 | 1 | 4 |
| Autotools | 2 | 3 | 5 |

这里的 CMake calibration `1` 只是 target-unresolved candidate 计数；它唯一对应 `gta-reversed`，不能通过
reference closure，不能解释为最终配额满足。

## 新的构造效度问题

`Hamlib/Hamlib` 两次默认构建都成功生成大量 x86_64 Linux ELF、共享库和静态库，但被
`freestanding_flags` 提升为 `stable_non_host_target`。日志中的 `-nostdlib` 来自 libtool 构建普通宿主共享库：
命令同时显式链接 Linux CRT 对象、`libstdc++`、`libc` 和 `libgcc_s`。因此“日志任意位置出现
`-nostdlib` 就证明 non-host”的规则过宽。

这个误分类不影响 CMake calibration 的 `0/1` 上界和停止决定，但说明 v5 target signal 不能原样推广到新的候选
池。若未来重新设计自然失败抽样，应让 non-host 信号绑定到具体 producer/产物或默认 endpoint，而不是对整段日志
做无作用域优先匹配。

## 支持与不支持的结论

本阶段支持：

1. 冻结 36 项中存在大量可重复的自然失败候选，数据稀缺不是唯一问题；
2. 固定角色分配下，CMake calibration 不可能满足 reference-eligible 配额；
3. 默认路径执行比 source-only 规则提供更多 endpoint 证据，但无作用域 target signal 仍会误判混合或普通宿主
   构建；
4. 当前自然失败三臂路线必须停止在 reference 和 Provider 之前。

本阶段不支持 Jev/Agent 在自然失败上的正负效果结论，不支持成本收益、模型排名、开放世界泛化或动态预算控制。
受控失败正式比较和混合工程链路的既有正向结论保持不变。

正式 JSON/Markdown、marker 和 raw evidence 永久只读；本审计不修改其标签或机械决定。

