# Jev 自然失败 Linux applicability v4 结果

- 状态：`completed`
- 决定：`proceed_to_natural_failure_build_reference_qualification_v4`
- 原始搜索结果：800；未见候选：586
- Linux-applicable 仓库：245；基础设施失败：0
- 平台不合格边：5；ambiguous 边：0
- build / Docker / credential / Provider / model token：0 / 0 / 0 / 0 / 0

- 回归资格：14/14

## 分配配额

| 构建系统 | eligible edge | 唯一分配 | 要求 |
| --- | ---: | ---: | ---: |
| cmake | 141 | 12 | 12 |
| make | 97 | 12 | 12 |
| autotools | 39 | 12 | 12 |

## 冻结项目

| 系统 | reserve 排名 | 项目 | exact commit |
| --- | ---: | --- | --- |
| cmake | 1 | `fastfloat/fast_float` | `033f64f6088bb00690858ce59bc8c7fd0566384a` |
| cmake | 2 | `adswill/onair` | `c47ee4b0cd13f4e6299311a2b41c4f5833604b65` |
| cmake | 3 | `nexyon/audaspace` | `73de966e3ef6b5f7fc9ccc1b74bb24edd18465aa` |
| cmake | 4 | `kimwalisch/primesieve` | `2d802722225c3a4a9cdaf8dff36b3ae58433cdb5` |
| cmake | 5 | `gta-reversed/gta-reversed` | `c85e5dcd9b7aa088e9e7a80f647d98bcd14a140f` |
| cmake | 6 | `sel4/sel4` | `6df0b6ee61f6a9e8a4ee7de8eb8fd698c0211b64` |
| cmake | 7 | `games-on-whales/wolf` | `541c541983b5705332f9e66333f7c0a3ed090ce6` |
| cmake | 8 | `tzcnt/toomanycooks` | `e6db2f6fdd9b0760437556d946ed7cbd7b01a5dd` |
| cmake | 9 | `shundhammer/myrlyn` | `99f025c8ae65e08b9dfa0d845b25626afdf75b94` |
| cmake | 10 | `jlblancoc/nanoflann` | `18f4edf753e813644a7a12711a86139777a8ef00` |
| cmake | 11 | `blazingrenderer/brender` | `d51add6f5c3a58efd7b9c3e453af4270b51c3f39` |
| cmake | 12 | `wangyu-/nc2000` | `11af316ed78aeba3f07cf82a8c99296ac4530d27` |
| make | 1 | `rbenhanced/rb3enhanced` | `b4678376f503744f8be2f6b0fea3cb56227415f7` |
| make | 2 | `multi-objective/moocore` | `e8340c83129469a5e370254cb0b7fef8a629b427` |
| make | 3 | `wuxb45/wormhole` | `9d3d0d0491410867b9f80b9be39d1782bcc7950c` |
| make | 4 | `tsotchke/eshkol` | `af1f761bef74889fa6c77ee9ded9cf2192f3caa4` |
| make | 5 | `rinnegatamante/vitagl` | `1a3b24765c0873f837ee0e8db4a554f01b8126c0` |
| make | 6 | `stella-emu/stella` | `5328270aea932db66d466314775b5707f45a3945` |
| make | 7 | `gamer92000/echo-dot-assist` | `64cb7ae4e775e507a7fdbfdfe7f552b5dea5227b` |
| make | 8 | `ceed/libceed` | `836ffed39188124a77dec7e75cc45b736db19eff` |
| make | 9 | `hhoppe/mesh-processing-library` | `a79b72ef6b23d2124071cf2a89c6e948a12cef78` |
| make | 10 | `manio/vdr-plugin-dvbapi` | `47a80f7c37d0d19a50c41941aec4d7ef7bdb3c0f` |
| make | 11 | `gbdev/rgbds` | `6818759a8ca8cd11bf092aa052e2a992b52ac8e5` |
| make | 12 | `marcjhuber/event-driven-servers` | `0a052f485e64b89b1d93875b3f80a2719a992ffc` |
| autotools | 1 | `jdolan/quetoo` | `46ea0a73099b82114685443cedc1a4aa25e8e3af` |
| autotools | 2 | `hamlib/hamlib` | `470518f35cfd6f3b1ce12a8d111e4bb2c1efd26d` |
| autotools | 3 | `nzjrs/osm-gps-map` | `acbfd5e34d3fe430b66ed1066a07e9d66324e1ef` |
| autotools | 4 | `openlightingproject/ola` | `6edf127a7c7f50c6428da58847b211f36d734cef` |
| autotools | 5 | `freebsd/kyua` | `220c2b24b53930b1ff34144f3a55227f597f8673` |
| autotools | 6 | `opensuse/snapper` | `6282061550c79f6fcd82778ac691c2236e415e77` |
| autotools | 7 | `starpu-runtime/starpu` | `08a475df516287852d24df46588c8c6e942672d9` |
| autotools | 8 | `ppp-project/ppp` | `4ff45106fba3c27c9dbedc03a751b77517597572` |
| autotools | 9 | `blackav/ejudge` | `5530ad931a60e70cdd406df41b96bd9420c33326` |
| autotools | 10 | `csete/gpredict` | `1d80049b0fecc06a18378d88f09b1d154a070234` |
| autotools | 11 | `c-icap/c-icap-server` | `a07ba7e51b03b3d665e936e95b157bfbf57ade9a` |
| autotools | 12 | `nickg/nvc` | `6f266eda11ea7aa92fec23866f633c48ee595d57` |

## 解释边界

本结果只评价 source-only Linux applicability 必要条件与采集隔离。它没有运行构建，不证明
Linux 构建成功、自然失败或 reference closure，也不评价 Jev、Agent、动作路由、成本收益或
动态预算控制。后续必须先做 build + reference qualification，再分配实验角色。
