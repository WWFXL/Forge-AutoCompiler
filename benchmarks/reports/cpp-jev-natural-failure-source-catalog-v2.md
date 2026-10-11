# Jev 自然失败 source catalog v2 结果

- 状态：`completed`
- 决定：`proceed_to_natural_failure_build_qualification_v2`
- 原始搜索结果：120；未见候选：109
- source eligible：53；基础设施失败：0
- build / Docker / credential / Provider / model token：0 / 0 / 0 / 0 / 0

## 分配配额

| 构建系统 | 合格分配 | 要求 |
| --- | ---: | ---: |
| cmake | 8 | 8 |
| make | 8 | 8 |
| autotools | 8 | 8 |

## 冻结项目

| 系统 | 排名 | 角色 | 项目 | exact commit |
| --- | ---: | --- | --- | --- |
| cmake | 1 | design | `zealdocs/zeal` | `f5dc479ba4dec5be5fe347971e0c19412843ee20` |
| cmake | 2 | design | `spotify/annoy` | `379f744667aba6b40ba3db8a07678df173a88f74` |
| cmake | 3 | calibration | `nicbarker/clay` | `e6cc36941ab2af5d81107617039d6f527a1c660b` |
| cmake | 4 | calibration | `hluk/copyq` | `8799bfeb9316bf79ce794f9a0325ee9dd2b18432` |
| cmake | 5 | evaluation | `winsiderss/systeminformer` | `d40ecb16a090dd234e819652fde9083807f0e58a` |
| cmake | 6 | evaluation | `tsl0922/ttyd` | `2922cb89f518bae4d0fcf4d757a7419638fc71fc` |
| cmake | 7 | evaluation | `alinshans/mytinystl` | `f86437ecffe8800cf247f9a21d55ee002d519e3f` |
| cmake | 8 | evaluation | `skywind3000/kcp` | `b1a7a2101dcbb96017681a500d6b82bbe5a88766` |
| make | 1 | design | `qinguoyi/tinywebserver` | `4bcf88762f85135e9bd46a1032e815e458de6f2e` |
| make | 2 | design | `leandromoreira/ffmpeg-libav-tutorial` | `82df59dffa161ef1cf47b86f6b958e7b2f78bb8a` |
| make | 3 | calibration | `sogou/workflow` | `3d5739960ac34d6164d5fec0abf268e83d72fe93` |
| make | 4 | calibration | `felixkratz/sketchybar` | `515046e8a150d6b8767a8a6dd624824eaafa2c8b` |
| make | 5 | evaluation | `snowie2000/mactype` | `05052e88c7ce134f93b66db95132284a1ed10de7` |
| make | 6 | evaluation | `mit-pdos/xv6-riscv` | `06aad25c735fd3159bdfae5680be4eab7b1668b2` |
| make | 7 | evaluation | `bol-van/zapret` | `c4d0b1990129dce2b28095277173ee0d7702d304` |
| make | 8 | evaluation | `apache/brpc` | `74e2c92654f07024d456e00e428eb5449ad5a810` |
| autotools | 1 | design | `memcached/memcached` | `2d51e364799bc9698bd4b11728ea978cea12da6e` |
| autotools | 2 | design | `mobile-shell/mosh` | `decd9b705eb81626f694335b8d5940538beb06da` |
| autotools | 3 | calibration | `jonas/tig` | `1700e4860d7f669ba71e88d9bace430e56cd7ebf` |
| autotools | 4 | calibration | `haiwen/seafile` | `0a4ec322cc654b903c163d52a019f798a0db5739` |
| autotools | 5 | evaluation | `openvpn/openvpn` | `66f8cdb9fd0b0334b6d79016b9d02cfceb6887d7` |
| autotools | 6 | evaluation | `twitter/twemproxy` | `60aaf855ba2e15e20d0efbe440c8ff071b719580` |
| autotools | 7 | evaluation | `jedisct1/libsodium` | `89e500718da7e1fc90e168bd88e18d1060f54db3` |
| autotools | 8 | evaluation | `citusdata/citus` | `d41eec345969a6d3d9d2dbb0d5c2e52b45ac62dc` |

## 解释边界

本结果只评价 source-only catalog 与采集隔离。它没有运行构建，不证明存在自然失败，也不评价
Jev、Agent、动作路由、成本收益或动态预算控制。根入口扫描不覆盖嵌套构建文件；后续 build
qualification 必须继续把运行时网络下载失败排除。
