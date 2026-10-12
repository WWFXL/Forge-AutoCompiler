# Jev 自然失败默认路径资格 v1

日期：2026-10-12。追踪：Issue #419。identity：`cpp-jev-natural-failure-default-path-qualification-v1`。

## 决定

`stop_natural_failure_build_reference_qualification_v1`。

## 正式观察

- 36 个冻结项目，完成 36 项；
- clean observation：72/72；
- 分类：`{"network_dependency_excluded": 1, "stable_failure_candidate": 23, "stable_host_userland_closure": 5, "stable_no_compiled_artifact": 2, "stable_non_host_target": 5}`；
- stable candidate 角色计数：`{"autotools": {"calibration": 3, "design": 2, "evaluation": 5}, "cmake": {"calibration": 1, "design": 2, "evaluation": 3}, "make": {"calibration": 1, "design": 2, "evaluation": 4}}`；
- infrastructure failure：0；
- cleanup 后 managed resource：0；
- 0 credential、0 Provider、0 model token。

## 未通过条件

- `known_non_host_not_excluded:gta-reversed/gta-reversed:stable_failure_candidate`

## 解释边界

本结果只判断固定候选能否形成足够的稳定默认路径失败候选。它不证明 reference 可闭合，也不评价 Jev、Agent、成本收益、模型排名或动态预算控制。
