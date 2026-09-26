# Stage C v1 源码获取中断审计

日期：2026-09-26。来源 identity：manifest canonical SHA-256 `6ef6f6fe9986ad6eb53d57273d4901389e96bff5b6b69d884d09282d391ac641`，release `80ac16d01741012327841a140be4e8bec978f165`。

## 结论

- 唯一 reachability 已通过，消耗 1 request / 70 recorded tokens。
- batch marker 已于 `2026-09-26T12:58:40Z` 创建，状态为 `started`。
- 第一项 `stage-c-json-c-r1` 的 A 臂在 `git fetch` 完成前中断；`FETCH_HEAD` 为空，没有检出 commit，也没有源码 export。
- runner 在源码获取之后才创建模型，因此正式 arm 的 Provider 请求、recorded tokens 和闭合 result 均为 0。
- v1 已形成未闭合 pair。依据预注册规则，v1 不得清理后续跑、补跑或导入到新结果。
- 停止后无 Stage C managed container 或 image。

## 实现缺口

v1 把网络源码获取直接写入正式 `pairs/{pair_id}/{arm}` 目录。进程在任何模型请求之前中断，也会留下非空 pair；后续执行必须 fail closed，但这把可恢复的前置基础设施故障升级成了整个 identity 的永久终止。

同时，v1 preflight 固定输出 `formal_stage_c_attempts=0`、`provider_calls=0` 和 `model_tokens=0`，没有复算已有 evidence，也没有把未闭合 pair 反映为 `ready=false`。

## 后续边界

新 identity 只允许改变运行编排与证据门禁：源码 clone、exact commit、源码 snapshot 和 build-system 检查必须在 create-once arm attempt marker 前完成。A/B 方法、任务、顺序、模型、镜像、预算、evaluator 和统计口径保持不变。v1 evidence 保持只读，新 identity 使用独立 evidence 目录并重新执行唯一 reachability 与全部 48 arms。

机器可读 inventory 与哈希见 `benchmarks/reports/cpp-stage-c-paired-calibration-v1-failed.json`。
