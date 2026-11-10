# 编译容器统一国内 HTTPS APT 源

本轮是基础设施修复，解决依赖网络干扰后续论文比较的问题；不产生新的模型效果或成功率结果。用户于2026-11-10要求编译容器统一国内HTTPS镜像，各比较方法共用配置。Issue #717；0 Provider、0新增模型费用。

## 修改与部署

- 默认使用 `https://mirrors.ustc.edu.cn/ubuntu/`，保留Ubuntu 24.04的 `noble/noble-updates/noble-backports/noble-security`、四个组件及原Ubuntu签名密钥；TLS和软件包签名校验保持启用。
- `docker/compile/ubuntu.sources` 作为完整编译镜像及只换源派生镜像的共同来源。`make compile-image` 默认使用该镜像站；可用 `APT_MIRROR` 显式指定另一域名，不接受在项目间选择不同初始源。
- 新增 `make compile-image-mirror`，只更新现有镜像的软件源并清空APT索引，不安装或升级软件包。默认产出 `autocompiler:gcc13-https-v1`，验证后再切换服务器默认标签。
- 从原镜像派生的新镜像保留所有旧层，250个已安装软件包名称/版本完全相同，排序清单SHA-256均为 `a4aad40515670b4ca6c59cc72a8c7a331b1ed06f89c68cb24c8ca9034d523aab`。
- 服务器 `autocompiler:gcc13` 已指向新镜像。旧镜像保留完整ID及 `autocompiler:gcc13-official-20261110` 标签；没有重启服务、修改宿主APT或兔兔云代理。

| 环境 | 镜像ID |
| --- | --- |
| 原官方源 | `sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a` |
| 新国内HTTPS源 | `sha256:8123220a201ac4d00cda0dc985b9db7227cd909bb93ca6c25fd82cafce5cd887` |

服务器派生构建命令：

```bash
make compile-image-mirror BASE_IMAGE=autocompiler:gcc13-official-20261110 COMPILE_IMAGE=autocompiler:gcc13-https-v1
docker tag autocompiler:gcc13-https-v1 autocompiler:gcc13
```

全新Ubuntu最小镜像缺少CA时，完整构建先通过国内HTTP源及Ubuntu签名索引安装 `ca-certificates`，随后恢复HTTPS再安装工具链；不关闭TLS校验。当前服务器使用已带CA的既有编译镜像派生，未经过该引导路径，也未执行整套工具链重装。

## 各方法使用同一环境

`scripts/forge_simple_system.py` 的Forge（基础/经验/Harness变体）与强工具Agent共同取 `task.image_id` 创建容器。`scripts/forge_simple_cxx_reference.py:resource_dockerfile` 使CXXCrafter的Dockerfile同样继承该ID；干净重放继续取原编译会话记录的同一不可变镜像ID。本轮没有改变这些方法的命令生成或恢复逻辑。

后续新比较须在所有方法的任务中统一绑定上表的新ID，并记录环境变更；只移动默认标签不会替换历史任务里已冻结的旧ID。旧manifest、源证据和失败保持原样，不用本轮安装检查回填ggmorse的旧失败。正在运行的旧容器不会因标签变化而切换环境。

## 实际验证

通过真实 `CompileDockerRuntime.create_container/create_replay_container` 创建两个独立、相同新镜像的容器，沿用已有运行时代理环境，依次更新索引并安装ggmorse原依赖集合：

```bash
apt-get -o Acquire::Retries=0 update --error-on=any
DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=0 install -y --no-install-recommends build-essential cmake git libsdl2-dev xorg-dev libglu1-mesa-dev
```

| 实际入口 | 更新索引 | 安装依赖 | 可用性与清理 |
| --- | ---: | ---: | --- |
| 编译容器 | 6.41秒 | 67.94秒 | SDL2/OpenGL pkg-config、GCC/CMake通过，容器已删除 |
| 独立重放容器 | 6.23秒 | 27.47秒 | 同上，容器已删除 |

每条命令保持180秒限制、无APT自动重试，全部退出0；两个容器实际镜像ID相同。这只验证原受阻依赖可在当前新环境安装，不证明ggmorse项目已构建成功，也不把第二次较快解释为方法加速。

新Docker集成检查1项、既有代理/Compose路径10项、CXX镜像装配1项通过；修改文件Ruff/格式检查通过。没有为此追加全产品重测或模型比较。完整Dockerfile冷构建未实跑；服务器已部署的是保持原工具链版本的派生路径。

原件位于服务器 `/home/yiwei/.codex/outputs/forge-compile-apt-mirror-20261110-v1/`：`scope.json`、`image-comparison.json`、`deployment.json`、`integration.log`及 `pytest/test_compile_and_clean_replay_0/mirror-check.json` 和各阶段日志。此前网络诊断另见 `/home/yiwei/.codex/outputs/forge-network-check-20261110T044321Z/`。
