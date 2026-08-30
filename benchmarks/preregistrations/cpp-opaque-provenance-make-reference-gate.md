# Opaque build provenance R2 Make reference gate

本门禁承接 Issue #200 的 R1 结果，但不读取 #190/#200 的模型正文或把两个 CMake pair 纳入新分析。目标是先定义 Make 的可信 provenance reference criterion，再决定是否值得创建第三个 checkpoint。当前固定 0 provider、0 credential read、0 Docker、0 checkpoint、0 formal attempt、0 model token 和 0 evidence write。

## Result-blind case

- 来源：`benchmarks/preregistrations/cpp-formal-v1-cases.json`，文件 SHA-256 `55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee`。
- Case：`https://github.com/kjdev/hoextdown@1ef9a71957570c2a65b7daa1b2f693ad87daf385`。
- Build system / workdir / target：Make、`/workspace/repo`、`libhoedown.a`。
- Build output / staged artifact / type：`libhoedown.a` / `libhoedown.a` / `static_library`。
- 依赖只有 `build-essential`。选择它是为了改变构建系统，同时减少依赖安装和 executable smoke-test 混杂。

固定提交的 upstream Makefile SHA-256 为 `534aa41e0ec89d2fcce9de0513a1f241ba965af568e801e089470301cc66288d`，明确声明 `libhoedown.a` target，并以 `ar rcs libhoedown.a $^` 生成产物。

## 成熟约定

GNU Make 官方 Options Summary 定义 `-C dir` / `--directory=dir` 为 Makefile 与 recipe 的有效目录，`-j [jobs]` / `--jobs[=jobs]` 只控制并发。SLSA Provenance v1.1 要求把外部构建参数纳入 provenance，并把 Git URI 解析到 exact commit。由此，Make P2 不能只相信模型声明的 `build` role，必须绑定 trusted executable、完整 argv、effective directory、target、repository、commit、image、physical attempt 与 artifact producer。

## P2 接受规则

可信 direct Make 必须满足：

- leaf executable 是 `make` 或 `gmake`；
- invocation workdir 与 `-C` / `--directory` 规范化后的 effective directory 精确等于 `/workspace/repo`；
- 只声明一个 target，且精确等于 `libhoedown.a`；
- 只额外允许 `-jN`、`-j N`、`--jobs=N` 或 `--jobs N`；
- 禁止变量赋值、额外 target 和未预注册选项；
- invocation 成功、未超时，artifact identity 与 output path 绑定到该 producer；
- repository、exact commit、image 和 physical attempt 与冻结 identity 一致。

满足全部规则时 P2 为 `proven / direct_make / trusted_direct_make_target`。顶层 `sh -c` wrapper 没有可信 leaf identity，必须保持 `unproven / opaque_wrapper`。目录、target 或 invocation 语义漂移均 fail closed；artifact/run identity 漂移属于证据无效，不降级为普通模型失败。

## 阶段边界

本 gate 复用现有版本化 invocation hash chain，但不修改冻结 CMake evaluator。成功只证明 Make reference criterion 与 result-blind candidate 在静态合同层成立，不证明真实 parent 能形成纯 fault，也不授权 reachability、模型 continuation 或 pair。下一阶段必须先做真实 Make lifecycle 的 0-provider fault-purity 与 cleanup 门禁。
