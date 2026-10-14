# H0/H1/H2 Runtime v6 十八臂 Provider 正式比较 v1 失败报告

**决定：`formal_execution_invalid_due_to_host_disk_exhaustion`。**

## 执行结果

Q0 通过并固定 release `213f2f232bf96a59897ec053e0a2b4a143d4f04b`、manifest canonical SHA-256
`ab8be962280f9b4d93a85e2d1632540ab1dfd57f3a9b927731f7a5929180a4d4`、三份 source archive、Docker image 和
Runtime v3/v4/v6 binding。Q0 为 0 credential read、0 Provider request、0 model token。

Q1 完成 8 个 arm 后，第 9 个 `autotools-expat/H1` 在模型请求前遇到宿主根分区写满，Python 返回
`OSError: [Errno 28] No space left on device`。错误发生后 arm result 和 Q1 result 的 create-once 写入也因同一原因失败；
两个零字节文件作为部分失败证据原样保留。第 10-18 个 arm 从未启动。

8 个完整 arm 描述性地均为 strict success，共 73 requests、490,354 recorded tokens、`$0.174662`。这些 observation
不构成平衡的 18-arm 分母，不得计算或报告 H2-H1 非劣、机制效果、成本差异或构建系统比较。

## 失败封口与修复

- 第 9 个 arm 与 Q1 marker 已标记为 `failed/OSErrorNoSpaceLeftOnDevice`；
- orphan managed compile container 已清理，封口时为 0 managed resource；
- credential 值与 Authorization/Bearer 文本扫描均为 0；
- raw evidence 为 4,595 files / 670,224,934 bytes，inventory canonical SHA-256
  `cc640491c3c8ff40039bbe2b225596723b026d6ba6e9b91b8ae558cf372b16b8`；
- 清理 51.24 GB 可再生 Docker build cache 后，根分区恢复约 47 GB 可用空间；未删除历史或当前 experiment evidence。

本 identity 永久只读，禁止续跑、补齐、替换、重分类或将 8 个完整 arm 导入后续效果估计。若继续正式比较，必须使用
全新 identity，并在 Q0 与每个 arm 前加入宿主剩余空间硬门禁。
