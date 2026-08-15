# Verifier-driven repair environment checkpoint 非模型原型预注册

## 研究问题

Issue #135 / PR #136 已证明 compiler 消息状态可以从同一个中性 SQLite checkpoint 派生两臂，但尚未证明编译环境可以从同一点恢复。本门禁只回答：显式暂停父容器后，分别冻结 rootfs 和 bind-mounted workspace/artifacts，能否恢复两个初始状态相同且可写层互不污染的 continuation arm。

## 冻结范围

- 跟踪 Issue：#137。
- 语言与任务范围：合成 C/C++ 编译环境 fixture，不运行真实仓库构建。
- Docker：仅使用 WSL2 Ubuntu 中由 `docker.service` 管理的原生 daemon；基础镜像使用本地 `autocompiler:gcc13`，运行时记录完整 image ID，不拉取镜像。
- Provider、模型 token、formal physical attempt：均为 0。
- 不修改生产 Compile Session、Oracle、clean replay、verifier-driven repair runner 或自然任务 ITT runner。
- attempt budget reconstruction 不属于本门禁，通过后另开阶段评审。

## 固定 capture 过程

1. 创建一个带独立 workspace/artifacts bind mount 的合成父容器。
2. 在父 rootfs 写 sentinel；在 bind mount 写普通文件、固定 mode/mtime 和符号链接。
3. 显式 `docker pause` 父容器。
4. 在同一个 pause 窗口内：
   - 使用 `docker commit --pause=false` 冻结 rootfs，并记录不可变 continuation image ID；
   - 使用只读 bind mount 的 helper container 分别生成 workspace/artifacts tar；
   - 固定 archive SHA-256 和逐项 manifest。
5. 无论 capture 成功或抛错，均在 `finally` 中执行 `docker unpause`。
6. 将 tar 与 checkpoint manifest 改为只读父快照。

## 固定恢复与比较过程

- baseline/treatment 从同一个 continuation image ID 和同一组只读 tar 恢复。
- 两臂使用不同 container identity 和不同可写 workspace/artifacts 目录。
- canonical 初始状态包含 image ID、rootfs sentinel hash，以及文件 path/type/content SHA-256/mode/mtime/uid/gid/symlink target。
- 初始 canonical 状态必须逐字相同，并与父快照 manifest 相同。
- 向 baseline 的 rootfs 与 workspace 写入后，treatment 和父状态必须不变。
- 向 treatment 的 artifacts 写入后，baseline 和父状态不得出现该文件。
- capture tar 和 manifest 的文件 hash 在两臂运行后必须不变。

## 通过条件

- 显式 pause capture 与异常 unpause 单元测试通过。
- tar manifest 固定普通文件内容、权限、mtime 与符号链接 metadata。
- 两臂 rootfs sentinel 恢复，且容器实际 image ID 等于同一 continuation image ID。
- 两臂初始 canonical 环境相同。
- rootfs、workspace、artifacts 的跨臂与父状态污染均为 0。
- 原型创建的 container、continuation image 和临时目录完成有界清理；不按宽泛 label 删除先前资源。
- provider calls、formal physical attempts 与 model tokens 均为 0。
- 聚焦单元测试、opt-in Ubuntu 原生 Docker 测试与 Ruff 通过。

## 失效条件

- Ubuntu 原生 Docker 门禁失败，或发现 Docker Desktop/其他 daemon 路径。
- 运行前已有 prototype label 资源；原型必须停止，不得做宽泛清理。
- 父容器未可靠 unpause，或 continuation image/任一容器未清理。
- 任一 metadata、内容 hash、rootfs sentinel 或 canonical state 不一致。
- 任一 arm 写入改变另一 arm、父目录或只读 snapshot。
- 发生 provider 请求、token 消耗或 formal physical attempt。

## 解释边界

通过仅证明“rootfs commit + bind tar”足以恢复本合成环境，并为后续 failure checkpoint 提供环境分支候选；不证明进程内存、网络连接、真实 compiler transcript、attempt budget 或 provider client 可以恢复，也不产生 repair packet 的因果效果结论。
