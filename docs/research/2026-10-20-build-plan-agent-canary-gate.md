# 双臂开发canary的零Provider接线门禁

Issue #486；真实身份 `cpp-build-plan-agent-canary-v1` 的前置工程门禁。固定miniz/md4c/pigz/libite各plan/tool两臂，8/8严格completed，原始源码哈希不变、固定完整测试、精确交付、同镜像clean replay和cleanup通过。0Provider、0模型tokens、0新增费用。

完整方案图脚本化提出一份方案；工具Agent图第一轮批量提出构建、固定测试和暂存，max_concurrency=1顺序执行，第二轮从权威记录取命令ID提交。验收成功即终止，没有为了取结束文本再调用模型。两臂均复用严格验收；工具臂不继承产品旧post-build次数限制。这里的1/2次脚本化请求只说明门禁接线，不能当真实调用节省证据。

修复消息计量中遗漏结构化输出工具schema的问题，并使工具臂在依赖、配置或重新构建后失效旧测试凭证。8项真实图、字节预算、usage与截断、固定oracle、精确交付、源码边界和类型化链接篡改回归通过。默认产品1875 passed/44 skipped，Ruff check及format通过；默认测试显式关闭Provider live调用。退出时旧Docker临时文件权限清理警告不改变测试结果，未改旧证据权限。

原始：`/home/yiwei/.codex/outputs/forge-plan-agent-canary-gate-v1/`。
新类型化封存3425普通文件、24 symlink、90,233,326 bytes，inventory canonical SHA-256
`accffb129476c01ea5a178b7044243f65ca9e973755f813376baf7a7bea42c15`。
外部独立审计：`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/plan-agent-canary-gate-v1-audit.json`，valid=true。
链接记录目标文本、不读取外部目标，旧身份封存规则和失败决定不变。

下一步按照冻结manifest/预注册，在共享$20授权内保留阶段$12后运行真实八臂。四项目已开发暴露，本地工具基线不等同所有强Agent。本canary只能检查运行闭合和描述，不支持总体非劣、机制增量或成本收益；没有恢复激活也如实报告。
