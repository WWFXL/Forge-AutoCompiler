# Forge 单 Agent Workflow Node Stage B 六项目授权校准

## 授权身份

- 父候选：`cpp-agent-workflow-stage-b-calibration-candidate.json`，canonical SHA-256 `303b41c0ee95c4732eb9388a39176789064e131c19217632175fa19e1526434f`。
- 授权基线：Phase 5 候选合并提交 `c12cb6096a53d976ad5cf767b42b2b0fb4ecdd4f`。
- 编译镜像：`autocompiler:gcc13`，完整 image ID `sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`。
- Provider：DeepSeek `deepseek-flash`，endpoint `https://api.deepseek.com`，0 retry、无 fallback、非 streaming。

授权修订不得改变父候选的六项目、exact commit、顺序、target、oracle、单项目预算、batch token ceiling 或停止规则。

## 执行顺序

1. 在合并后的干净 `main == origin/main` 上完成 0 Provider preflight。
2. 只允许一次 reachability，请求内容固定为 `Reply with exactly CANARY_OK and nothing else.`，最多记录 5,000 tokens。
3. reachability 通过后，按 `yyjson`、`cppitertools`、`openh264`、`uwebsockets`、`c-ares`、`libass` 顺序各运行一个 physical attempt。
4. 每个 attempt 必须完成 Agent Workflow Node、外部 S0-S5 evaluator、clean replay、finalize、cleanup 和 0 orphan 检查，才允许创建下一个 attempt。
5. 六项目终态齐全后生成 batch report 与 Stage C 决策包。

## Evidence 与恢复

- evidence 根沿用父候选冻结的新目录，不读取或写入 CXXCrafter 历史 evidence。
- reachability、batch 和 task marker 采用 create-once；报告采用 create-once；marker 只允许同 identity 从 `started` 转入 `passed` 或 `failed`。
- batch 重启只跳过已有完整、同 manifest、同 release 且 cleanup 闭合的连续任务前缀。发现未闭合 attempt、乱序结果或 identity 漂移时停止，不创建 replacement。
- 每项目独立报告 `candidate_generated_observed`、`candidate_submitted`、S0-S5、`strict_reproducible_build_success` 和 `bitwise_reproducible`。

## 解释边界

- 六项目结果仅用于工程校准、轨迹分析和 Stage C 决策，不作为新方法的无偏成功率。
- 不根据任何单项目结果修改公共 prompt、工具、预算、顺序、oracle 或终止规则。
- 必须修改通用机制时，当前 identity 终止，并通过新版本协议重新校准。
