# Stage C v6 零 Provider 离线定向重评结果

本报告是对 v5 中 22 个已提交 B 臂候选的事后测量修复敏感性分析。它不替代 v5 正式结果：A 臂仍为 `19/24`，B 臂仍为 `0/24`。

22 条重评中 strict success 为 `18/22`，bitwise reproducible 为 `21/22`。本阶段没有 Provider 请求，input/output/total token 均为 0；22 条 cleanup 全部闭合，结束时 0 managed resources。

| Project | Strict success | Replicates |
| --- | ---: | --- |
| `8cc` | 2/2 | r1=pass, r2=pass |
| `json-c` | 1/2 | r1=pass, r2=fail |
| `leveldb` | 2/2 | r1=pass, r2=pass |
| `libjpeg-turbo` | 1/2 | r1=pass, r2=fail |
| `libsndfile` | 2/2 | r1=pass, r2=pass |
| `libsoundio` | 2/2 | r1=pass, r2=pass |
| `lz4` | 2/2 | r1=pass, r2=pass |
| `oatpp` | 1/2 | r1=pass, r2=fail |
| `rnnoise-0.1.1` | 2/2 | r1=pass, r2=pass |
| `stockfish-11` | 2/2 | r1=pass, r2=pass |
| `theora` | 1/2 | r1=fail, r2=pass |

两次未生成候选的 CivetWeb attempt 不在重评分母中。22 个 attempt 也不能作为 22 个独立项目解释。
