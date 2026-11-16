# libffi真实宏与Agent宏的后验功能验证

2026-11-16；Issue770；用户批准下一项零模型费用尝试。身份cpp-build-libffi-functional-comparison-v1，0Provider/0美元，不读取凭据，不新增模型效果或独立项目分母，不改旧原件或论文。

同E57 libffi commit、原归档及不可变镜像（tasks.json中的libffi），两条新路径各一次，均autogen、configure --disable-docs、make -j2；国内HTTPS镜像与CPU2/内存4G/网络相同。A安装真实libltdl-dev；B复制上一单次自主轨迹最终宏，不注入其他修复。每命令最多600秒，失败保留、不自动重试；所有已创建容器finally清理。

比较有效fficonfig.h宏定义、公开头文件、动态导出/静态全局符号名称及类型；不要求二进制字节一致。相同C程序覆盖整数、浮点、结构体传参/返回、变参、closure回调五场景，各跑新A/B静态/动态链接四个程序。另对上一轮原始静态/共享产物的只读副本跑相同探针两个程序，核验动态链接实际本地库而非系统库。保留编译/调用准备检查的具体输出。成功支持当前平台这些场景及可观察配置一致，不证明跨平台/全ABI等价，不把人工路径当Agent自主诊断效果。

原件输出单独新目录forge-libffi-functional-comparison-2026-11-16-v1；复用前轮只读快照，完整命令、日志、构建目录、符号、配置、程序源码及产物和清理记录保存。任何发现通过新报告解释，不修改冻结source_review标记。
