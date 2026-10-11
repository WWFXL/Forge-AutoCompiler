# Jev 自然构建失败 source qualification v2 结果

- 状态：`completed`
- 决定：`proceed_to_reference_recipe_qualification_v2`
- 项目：24/24；稳定自然失败：17
- Provider：0 request / 0 token；credential：0 read

## 角色配额

| 构建系统 | design | calibration | evaluation |
| --- | ---: | ---: | ---: |
| cmake | 1 | 1 | 3 |
| make | 1 | 1 | 4 |
| autotools | 2 | 1 | 3 |

## 项目结果

| 项目 | 系统 | 角色 | 分类 | 失败阶段 / 类别 |
| --- | --- | --- | --- | --- |
| `cmake-zealdocs-zeal` | cmake | design | `stable_natural_failure` | configure / missing_dependency |
| `cmake-spotify-annoy` | cmake | design | `initial_success` | - |
| `cmake-nicbarker-clay` | cmake | calibration | `network_dependency_excluded` | - |
| `cmake-hluk-copyq` | cmake | calibration | `stable_natural_failure` | configure / missing_dependency |
| `cmake-winsiderss-systeminformer` | cmake | evaluation | `stable_natural_failure` | configure / unknown_build_failure |
| `cmake-tsl0922-ttyd` | cmake | evaluation | `stable_natural_failure` | configure / missing_dependency |
| `cmake-alinshans-mytinystl` | cmake | evaluation | `initial_success` | - |
| `cmake-skywind3000-kcp` | cmake | evaluation | `stable_natural_failure` | configure / unknown_build_failure |
| `make-qinguoyi-tinywebserver` | make | design | `stable_natural_failure` | build / missing_dependency |
| `make-leandromoreira-ffmpeg-libav-tutorial` | make | design | `initial_success` | - |
| `make-sogou-workflow` | make | calibration | `initial_success` | - |
| `make-felixkratz-sketchybar` | make | calibration | `stable_natural_failure` | build / compile_error |
| `make-snowie2000-mactype` | make | evaluation | `stable_natural_failure` | build / unknown_build_failure |
| `make-mit-pdos-xv6-riscv` | make | evaluation | `stable_natural_failure` | build / compile_error |
| `make-bol-van-zapret` | make | evaluation | `stable_natural_failure` | build / missing_dependency |
| `make-apache-brpc` | make | evaluation | `stable_natural_failure` | build / configure_required |
| `autotools-memcached-memcached` | autotools | design | `stable_natural_failure` | configure / compile_error |
| `autotools-mobile-shell-mosh` | autotools | design | `stable_natural_failure` | configure / compile_error |
| `autotools-jonas-tig` | autotools | calibration | `initial_success` | - |
| `autotools-haiwen-seafile` | autotools | calibration | `stable_natural_failure` | configure / compile_error |
| `autotools-openvpn-openvpn` | autotools | evaluation | `stable_natural_failure` | configure / compile_error |
| `autotools-twitter-twemproxy` | autotools | evaluation | `initial_success` | - |
| `autotools-jedisct1-libsodium` | autotools | evaluation | `stable_natural_failure` | configure / missing_dependency |
| `autotools-citusdata-citus` | autotools | evaluation | `stable_natural_failure` | configure / compile_error |

## 解释边界

本结果只判断冻结项目能否形成稳定自然失败来源。网络、平台、超时和基础设施失败均不计入；
它不验证 reference recipe、动作矩阵、Jev/Agent 效果、成本收益或动态预算控制。
