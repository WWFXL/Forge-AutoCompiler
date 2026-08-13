# Forge C/C++ formal 模型请求 300 秒超时校准结果

> 本报告由只读结果分析器从冻结 manifest 和 append-only ledger 确定性生成。

## 摘要

- 完成 2/2 个授权 slot，Oracle 通过 2/2。
- 23/23 模型请求闭合，记录 142,502/500,000 tokens，orphan=0。
- 最大请求延迟 33.891 秒；超过 120 秒 0 次，超过 300 秒 0 次。
- 本批证明 300 秒配置路径可完整运行；没有请求超过 120 秒，因此没有观察到超时延长实际挽救慢请求。

## 每个条件

| Condition | 请求闭合 | 最大延迟 (s) | >120s | >300s | Oracle | Tokens | Wall time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `richlab-gpt-5.5` | 9/9 | 33.891 | 0 | 0 | pass | 42,063 | 245.157 |
| `deepseek-v4-flash` | 14/14 | 5.896 | 0 | 0 | pass | 100,439 | 150.388 |

## 研究边界

- 结果为 descriptive-only，不进入 formal 模型能力主比较，也不能用于两个模型的总体排名。
- 单一项目、每个 provider 一次 attempt 不能估计长期网络稳定性或超时参数的因果效应。
- 没有 retry、fallback、replacement 或 backfill；旧失败 canary 与本修订层分别保留。

## 复算

```bash
/app/backend/.venv/bin/python /repo/scripts/forge_formal_timeout_calibration_result.py \
  --manifest /repo/benchmarks/manifests/cpp-formal-timeout-canary-amendment.json \
  --evidence-dir /workspace/.compile-sessions/benchmark-evidence-formal-timeout-canary-amendment
```
