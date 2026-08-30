# Forge opaque provenance 六 case confirmatory candidate v2 amendment

- GitHub Issue：[Issue #233](https://github.com/WWFXL/Forge-AutoCompiler/issues/233)
- 父协议：Issue #230 candidate v1
- 状态：pre-result、未授权、零 provider

## 触发原因

Issue #232 的 Ubuntu-native Docker lifecycle gate 发现 `sql-parser-shared` 在相同 exact commit 和 image 下间歇性 clean replay SHA-256 mismatch。失败产物与接受产物的相对路径、ELF shared-library 类型和字节大小一致，只有内容哈希与 GNU build-id 不同。

隔离双 checkout 显示 `make library` 会受 checkout mtime 顺序影响：一条路径重新运行 Bison 生成 `bison_parser.cpp/.h`，另一条路径直接消费仓库内已跟踪生成文件。空 bootstrap 因而没有冻结真实源码生成路径。发现与诊断均发生在任何新 case provider 结果之前。

## 唯一语义修正

v1 manifest、schema 和 preregistration 保持逐字不变。v2 机械继承六 case、12-pair schedule、analysis、runtime、measurement 与全部关闭的 authorization，只把 `sql-parser-shared.bootstrap_commands` 从空数组改为：

```bash
cd src/parser && bison bison_parser.y --output=bison_parser.cpp --defines=bison_parser.h --verbose
```

该命令与上游 Makefile 的生成命令一致，并在每次 build 前无条件选择同一源码生成路径。Lifecycle adapter 在 self-contained parent wrapper 中用独立 subshell 执行 bootstrap，避免 `cd` 改变后续 Make workdir。

## 不变项

- Repository、exact commit、Make target `library`、artifact `libsqlparser.so` 与 shared-library oracle 不变。
- 其余五个 case 逐字不变。
- 12-pair 顺序与 schedule identity 不变。
- Production artifact type/size/SHA、clean replay 和 cleanup 语义不变；不放宽 verifier。
- Provider、credential、Docker、checkpoint、pair collection、formal attempt、evidence write 与 model token 授权仍全部关闭。

## 停止规则

只有 v2 相对 v1 的允许差异合同、`sql-parser-shared` 连续 lifecycle 稳定性门禁和完整六 case lifecycle 门禁都通过后，v2 才可成为未来 execution amendment 的父候选。若仍出现 SHA mismatch，必须排除该 case 并重新选择 Make project block；不得继续叠加 touch、strip 或 verifier 例外。
