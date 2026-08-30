# OpenH264 独立 Make checkpoint 零 provider candidate

- Issue：[#224](https://github.com/WWFXL/Forge-AutoCompiler/issues/224)
- 性质：result-blind、零 provider、零凭据读取、零 model token 的 candidate/lifecycle 门禁。
- 历史边界：#218 hoextdown pair 保持机制无效终态，本候选不是 retry、replacement 或 backfill。

## 候选择取

从冻结的 `cpp-formal-v1-cases.json` 审计 Make cases。`openh264@4a2615fac570c6ca1ed4f157b9fdab9466edfd80` 只在历史 manifest 出现；本地 append-only physical evidence 与已发布 report 均没有该 case。固定提交只有一个根 `Makefile` 且无 submodule，`libopenh264.a` target 与单一 static-library oracle 直接对应；固定 OSS-Fuzz recipe 也调用同一 target。

暂不选择：

- `sql-parser`：`library` 默认产出 shared library，要得到 oracle 中的 `.a` 还需额外 `static=yes`；
- `lodepng`：OSS-Fuzz recipe 绕过 Make，且 executable smoke 会引入额外终态语义。

## 冻结构造

- repository：`https://github.com/cisco/openh264`
- commit：`4a2615fac570c6ca1ed4f157b9fdab9466edfd80`
- build directory：`/workspace/repo`
- direct target / output / staged artifact：`libopenh264.a`
- system packages：`build-essential`、`nasm`
- jobs：可省略或为 `1..2`；无界、0、超限或 target drift 均 fail-closed
- parent：opaque shell wrapper，产物存在但 P2 为 `build_system_unproven`
- treatment：独立 direct Make 与 artifact stage，P2 必须转换为 `direct_make`
- repair packet：唯一 treatment exposure，不包含 command、argv、shell 或凭据

## Agent construction 与 lifecycle

候选把 OpenH264 action policy 注入 #220 已修复的组合 bindings，并复用 #222 的完整 `create_agent + ThreadState + InMemorySaver` fake-model 门禁。成功路径必须精确产生一个 request started/completed，异常路径和 cleanup 路径必须释放所有 active context。

真实 Docker gate 是 opt-in，只使用 Ubuntu WSL2 原生 daemon。仓库基础编译镜像不含 `nasm`，因此 gate 临时派生一个只增加 `nasm 2.16.01-1build1 amd64` 的 image；固定 `.deb` 的 SHA-256 为 `22eede0f2dd62343b0298182f62f7485704fe02f166395b02c92a8883377e0b3`，下载上限 60 秒，禁止下载 apt index。parent、baseline、treatment 与 clean replay 共用其不可变 image identity，结束后删除派生 image。该 fixture 不修改生产镜像，也不把 dependency setup 暴露给 post-checkpoint treatment。

## 授权与结论边界

本阶段不创建 checkpoint、provider model、reachability、behavioral pair 或 formal evidence，model-token authorization 为 0。即使门禁通过，也只能说明新 case 的构造与 lifecycle 可执行；后续 provider amendment 必须另建 Issue、manifest、evidence identity 和一次性停止规则。单 pair 只做描述性机制复制，不与历史 case 池化，不计算 p 值，不排名模型。
