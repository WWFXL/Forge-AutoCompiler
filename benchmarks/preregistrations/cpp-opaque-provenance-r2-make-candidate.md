# Opaque build provenance R2 Make 单配对未执行候选

本候选承接 Issue #202 的 Make P2 reference criterion 与 Issue #204 的真实零 provider lifecycle gate。当前只冻结一个新的 Make state-matched pair，不创建 checkpoint，不调用 provider，不启动 Docker，也不写正式 evidence。

## Case 与机制

- Result-blind case：`https://github.com/kjdev/hoextdown@1ef9a71957570c2a65b7daa1b2f693ad87daf385`。
- Build system / directory / target：Make、`/workspace/repo`、`libhoedown.a`。
- Output / staged artifact / type：`libhoedown.a` / `libhoedown.a` / `static_library`。
- Parent 必须保持 `unproven / opaque_wrapper`；treatment 唯一额外 exposure 是原九字段 repair packet，不提供完整命令。
- 双臂顺序固定为 `baseline -> treatment`，message/environment/budget state-matched；4/2/2/2 action limits、原子 claim、`parallel_tool_calls=false`、R0 companion、candidate、clean replay 与 cleanup 保持不变。

## Provider 与预算候选

为与 R1 yyjson 进行同模型、跨构建系统的描述性复制，候选固定 DeepSeek `deepseek-v4-flash`、`https://api.deepseek.com`、300 秒、0 retry、非 streaming、禁止 fallback。每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间、120 秒 cleanup reserve 和 120,000 recorded tokens；reachability 5,000、pair 240,000、阶段 ceiling 245,000。

## 当前边界

Issue #206 只开放 `validate`、`plan` 和只读 `preflight`。Checkpoint、reachability、provider、formal attempt、pair、credential、model、Docker 与 evidence write 全部关闭，model token 授权为 0。未来真实执行必须另建 execution amendment；该单 pair 只描述 cross-build-system P2 conversion replication，不估计 treatment effect、不计算 p 值、不排名模型、不池化 #190/#200。
