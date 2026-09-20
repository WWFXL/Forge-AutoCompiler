# 真实过程正文与可折叠导出报告实施计划

日期：2026-09-20。设计：`../specs/2026-09-20-processing-narration-export-report-design.md`。状态：**本地实现与验证完成，待 PR 交付**。

## 1. 交付范围

本计划通过一个小而完整的 PR 交付：

- 修复 processing group 丢弃真实 AI `content`；
- 原始 reasoning 单独折叠且不翻译；
- Markdown 将工具结果和证据改为按项折叠；
- 新增自包含 HTML 报告；
- 当前会话与历史列表两个导出入口行为一致；
- 新增 Runtime v6 工程身份和相关文档。

不修改模型提示词、编译后端、证据内容或历史 Runtime；不运行 provider 和正式实验。

## 2. 强制顺序

- [x] 核对真实服务器 Thread，证明中文 content 与英文 reasoning 同时存在。
- [x] 创建并回读中文 Issue #277。
- [x] 从最新 `main@e7c93d1d` 建立独立分支。
- [x] 完成 Spec 与 Plan。
- [x] 先补充失败测试，固定 content 不消失、无合成 fallback 和折叠导出契约。
- [x] 实现实时消息展示。
- [x] 实现 Markdown/HTML 导出和双入口菜单。
- [x] 更新 Runtime v6、文档与项目快照。
- [x] 运行逻辑、lint、typecheck、format、build 和浏览器回归。
- [ ] 中文提交、通过 WSL Git 推送、创建并回读 PR。
- [ ] CI 全绿后合并，核对 Issue 和远端 main。

## 3. Phase A：失败测试

1. 在消息测试中构造 `content + reasoning_content + tool_calls` 的真实 DeepSeek 形状。
2. 在离线浏览器 fixture 中分两段返回同一消息：先有 content，随后增加 tool call。
3. 断言中文 content 在稳定终态仍存在，原始推理默认不可见、展开后可见。
4. 构造 content 为空的消息，断言没有 narration 或前端合成文本。
5. 为 Markdown 固定成对 tool call/result、未匹配结果、成功/失败命令和长日志。
6. 为 HTML 固定包含 `</script><img onerror=...>` 的不受信任文本，断言只以文本出现。

完成门：新断言在现有实现上按预期失败，且失败原因指向本轮行为。

## 4. Phase B：实时界面

候选文件：

- `frontend/src/components/workspace/messages/message-group.tsx`
- 必要时新增纯逻辑消息步骤模块及测试
- `frontend/src/core/i18n/locales/{types,zh-CN,en-US}.ts`
- `frontend/scripts/test-compile-trace-layout.cjs`

任务：

1. processing steps 支持真实 narration/content 类型。
2. 同一 AI 消息按 content、raw reasoning、tool calls 建立稳定步骤，不修改 Message。
3. narration 使用 MarkdownContent 展示；空 content 不创建步骤。
4. raw reasoning 使用明确的国际化标题且默认折叠。
5. 保持 tool call/result 的 ID 配对、late result 回填和 subagent 卡行为。
6. 验证长中文、英文 reasoning、桌面/手机/短屏均无覆盖。

完成门：Node 消息测试和离线 trace Playwright 通过。

## 5. Phase C：统一导出渲染

候选文件：

- `frontend/src/core/threads/export.ts`
- 新增 `frontend/src/core/threads/export.test.ts`
- `frontend/src/components/workspace/export-trigger.tsx`
- `frontend/src/components/workspace/recent-chat-list.tsx`
- `frontend/scripts/test-compile-export.cjs`
- i18n locale/type 文件

任务：

1. 建立纯函数工具关联结构，以 `tool_call_id` 配对调用和结果。
2. Markdown 中正文默认展开，reasoning、工具、命令、日志、replay 和 raw Session 使用 `<details>`。
3. 已匹配 ToolMessage 不再作为独立顶级章节重复；未匹配结果显式保留。
4. 新增 HTML escape、属性 escape 和安全 JSON/text `<pre>` helpers。
5. 生成含内联 CSS 的完整 HTML 文档；不引用外部资源。
6. 加入 HTML 下载函数和两个导出入口的菜单项。
7. JSON renderer 保持字段和值不变。

完成门：纯逻辑测试验证完整性、折叠结构与注入防护；浏览器实际下载三种格式并离线打开 HTML。

## 6. Phase D：Runtime v6 与文档

1. 保留 `compile-runtime-v5.json`、`docs/compile_runtime_v5.md` 和历史身份字节不变。
2. 新增 `compile-runtime-v6.json` 与 `docs/compile_runtime_v6.md`，predecessor 固定本轮 main。
3. 扩展 identity 测试：v5 从 predecessor Git blob 审计，v6 哈希匹配当前产品组件。
4. 更新前端开发说明、README 中文导出说明和 `.claude/memory/project.md`。
5. 明确 v6 仅允许 interactive product validation。

## 7. Phase E：验证矩阵

按风险递增执行：

1. frontend Node 消息与导出纯逻辑测试；
2. Prettier、ESLint、TypeScript；
3. `BETTER_AUTH_SECRET=local-dev-secret pnpm build`；
4. 离线 Playwright：实时 trace、当前会话导出、历史导出、HTML 离线展开与注入检查；
5. Runtime identity 与 frozen predecessor pytest；
6. `git diff --check` 和改动范围审计；
7. 干净 GitHub CI。

测试不连接模型、不创建 Compile Session、不写正式 evidence。

## 8. 提交、PR 与合并

1. 以中文提交 spec、实现、测试和文档。
2. 使用 `scripts/push-via-wsl.ps1` 推送。
3. 创建中文 PR，正文包含 `Closes #277`、根因、真实行为、测试证据和实验边界。
4. 回读 PR，等待 backend/frontend/frozen CI 全绿。
5. 合并后核对 PR、Issue、远端 main SHA，并给出服务器拉取和重建命令。

## 9. 停止条件

遇到以下情况停止扩大范围并报告：

- 需要修改 v5 或更早 Runtime identity/evidence；
- 必须调用真实 provider 才能建立测试；
- HTML 需要新增大型 Markdown/HTML 运行依赖；
- 需要放弃 HTML escape 或执行仓库提供的脚本才能展示报告；
- 导出证据必须绕过现有 Gateway 边界才能完整读取。
