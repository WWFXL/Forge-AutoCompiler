# 规划工具约束与P4：36槽派生分析

原件只读；`analysis.json`复制冻结分析，`verification.json`为独立原事件计量及清理核验。`failure-excerpts.txt`保留五个未完成槽原始错误摘要，`slots.csv`保留完整分母。

原件：`/home/yiwei/.codex/outputs/forge-planning-tool-p4-comparison-flash-v1`。inventory SHA-256：`cc85f9d841f16e18e6c0c3f756777c37e4ffd0e4147be9c500ba6407647457b9`。

解释及共同完成子集见[结果报告](../../../docs/research/2026-11-12-planning-tool-p4-comparison-results.md)。

|槽|项目|方法|主构建及交付完成|请求（初始/恢复）|美元|秒|
|---|---|---|---|---|---|---|
|1|open62541|A_P0_schema|未完成|50（50/0）|0.1893384|78.12|
|2|open62541|B_P0_enforced|是|36（15/21）|0.1436712|110.81|
|3|open62541|C_P4_enforced|未完成|71（39/32）|0.2824317|150.03|
|4|lz4|C_P4_enforced|是|2（2/0）|0.0064608|31.46|
|5|lz4|B_P0_enforced|是|2（2/0）|0.0064368|33.10|
|6|lz4|A_P0_schema|是|2（2/0）|0.0063066|31.12|
|7|libusb|B_P0_enforced|是|11（11/0）|0.0493644|118.58|
|8|libusb|C_P4_enforced|是|3（3/0）|0.012093|70.01|
|9|libusb|A_P0_schema|是|4（3/1）|0.0172347|85.59|
|10|libde265|A_P0_schema|是|2（2/0）|0.0071889|49.32|
|11|libde265|C_P4_enforced|是|1（1/0）|0.0037317|48.06|
|12|libde265|B_P0_enforced|是|3（3/0）|0.0117582|51.04|
|13|clib|C_P4_enforced|是|6（6/0）|0.0164127|58.39|
|14|clib|A_P0_schema|是|5（5/0）|0.0133737|55.22|
|15|clib|B_P0_enforced|是|6（6/0）|0.0177651|64.14|
|16|libffi|B_P0_enforced|未完成|23（3/20）|0.1459791|334.72|
|17|libffi|A_P0_schema|未完成|49（9/40）|0.2827953|541.25|
|18|libffi|C_P4_enforced|未完成|45（3/42）|0.2832684|603.58|
|19|libsndfile|A_P0_schema|是|3（3/0）|0.0131295|86.06|
|20|libsndfile|B_P0_enforced|是|10（10/0）|0.0417759|97.25|
|21|libsndfile|C_P4_enforced|是|7（7/0）|0.0304158|94.60|
|22|streem|C_P4_enforced|是|2（2/0）|0.0033822|33.82|
|23|streem|B_P0_enforced|是|4（4/0）|0.0075081|42.37|
|24|streem|A_P0_schema|是|3（3/0）|0.0041931|16.69|
|25|wolfssl|B_P0_enforced|是|3（3/0）|0.0119268|171.99|
|26|wolfssl|C_P4_enforced|是|3（3/0）|0.0111759|163.99|
|27|wolfssl|A_P0_schema|是|3（3/0）|0.0113448|168.04|
|28|mbedtls|A_P0_schema|是|1（1/0）|0.0036681|89.45|
|29|mbedtls|C_P4_enforced|是|1（1/0）|0.003717|88.23|
|30|mbedtls|B_P0_enforced|是|2（2/0）|0.0085608|93.66|
|31|libtomcrypt|C_P4_enforced|是|4（4/0）|0.0113355|51.18|
|32|libtomcrypt|A_P0_schema|是|6（6/0）|0.0163041|53.31|
|33|libtomcrypt|B_P0_enforced|是|4（4/0）|0.0098886|50.81|
|34|cava|B_P0_enforced|是|9（3/6）|0.0425289|89.43|
|35|cava|A_P0_schema|是|4（4/0）|0.0191664|214.62|
|36|cava|C_P4_enforced|是|7（7/0）|0.0298791|66.40|
