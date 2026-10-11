# Jev 自然失败 Linux applicability v3 构造效度审计

日期：2026-10-12。追踪：Issue #415。被审计 identity：
`cpp-jev-natural-failure-linux-applicability-v3`。

## 结论

v3 的正式停止决定保持成立，但门禁实现本身没有通过构造效度审计。正式运行标记了 7 条
`platform_ineligible` 边；逐项读取 exact commit 的根入口和文档后，5 条是明显误伤，只有 2 条应当排除。
因此不能声称 v3 已可靠解决 macOS/Windows 局部配置污染 Linux 样本的问题，也不能把它用于冻结后续实验角色。

同时，停止决定不依赖这 5 个误伤：79 个 `source_eligible` 仓库中，CMake、Make、Autotools 的可用项目边分别为
38、39、8，Autotools 仍低于预注册的 12。分配器优先填充最稀缺系统，在 Autotools 8 个耗尽后停止，因此正式
报告中的 CMake `0`、Make `0` 是未完成的冻结分配数，不是找到的候选数。

## 证据完整性

- 正式 execution revision：`2ac9d4982bb9e3182b468c85d9da3a52c5dcdb85`；
- evidence：202 files / 447,440 bytes，canonical SHA-256
  `ba254ab6c173c5f2bae89ee4968cc51854e9d9f4300ed420fd538a4704266d6b`；
- 正式 JSON/Markdown SHA-256：`723c02cdecf3f351f9a707ebbaca85245cd45e554fdc0895f97a416b49e67435` /
  `6d72851a2cb1915176eccab47790c507714b71ed6f7fc3770ff16f495374122b`；
- `audit` 返回 `valid=true` 且无错误；
- 7 个排除项目的 16 个入口/文档 blob 均从记录的 exact commit 重新读取，内容 SHA-256 全部与正式 evidence 匹配；
- v1/v2 catalog 和 build qualification inventory 保持
  `d561e612515b5378a8ab2f6ab7cb6e94beb0b305229e15b1bd52a01aafd59736` /
  `d2c61123506f80dd925f4df20e12bd1c613bb46959ab1ccc401f90d90ea1d658`。

## 排除复核

| 项目 | 系统 | 审计判断 | 依据 |
| --- | --- | --- | --- |
| `jondgoodwin/cone` | CMake | 误伤 | README 有完整 Ubuntu/Linux 构建命令；“Windows only”只修饰部分 OS 包。 |
| `LIJI32/SameBoy` | Make | 误伤 | 非 Darwin 默认构建 SDL，`all` 产生宿主二进制，并有 Linux install 路径；Apple 工具在条件分支。 |
| `metroidret/mf` | Make | 应排除，但原理由错 | 默认产物是 GBA ROM且依赖 `arm-none-eabi`；“WINDOWS ONLY”修饰的是 WSL 安装步骤。 |
| `mist-devel/mist-firmware` | Make | 应排除 | 默认固定 `arm-none-eabi` 并产生 firmware hex/bin/upg。 |
| `redhat-et/ripwire` | CMake | 误伤 | 发布 Linux arm64/x86-64 二进制；`xcrun`/OSX sysroot 位于注释或 Apple 条件逻辑。 |
| `SpeedBreakerProject/speedbreaker` | CMake | 误伤 | README 有原生 Linux/SteamOS 构建命令；“only on macOS”只描述一个局部依赖构建。 |
| `Wallawalla47/Infernix` | CMake | 误伤 | README 明确支持原生 Linux；`MSBuild` 只出现在注释，Ninja 路径有效。 |

## 失败机制

v3 对整个入口文件和整篇文档运行无作用域正则。它没有剥离注释，也没有区分条件分支、局部能力描述和项目级
平台声明；虽然采集了 `document_linux_signals`，分类决策并未使用该字段。结果是“文件中存在 Apple/Windows
词语”被错误提升为“根入口只能在该平台执行”。此外，宿主平台与产物终点混在同一组 strong signal 中，使
`metroidret/mf` 虽然被正确排除，却记录了错误的主要理由。

## 解释边界与下一步

本审计证明 v3 classifier 的假阳性不可接受，并确认当前按更新时间排序的 200 项搜索框只有 8 个 Autotools
候选。它没有执行构建，不证明 Linux 构建成功、自然失败、reference closure，也不评价 Jev、Agent、动作路由、
成本收益或动态预算控制。

v3 identity、report、marker 和 raw evidence 永久只读。继续修复必须使用新 identity：分别判断 Linux 宿主支持和
非宿主终点，扫描前剥离注释，让明确 Linux 路径否决局部 Apple/Windows 信号，并扩大未见搜索框解决 Autotools
稀缺；v3 已观察的全部项目族不得作为新 identity 的结果样本。
