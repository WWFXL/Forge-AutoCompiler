# Forge-AutoCompiler Frontend

Forge-AutoCompiler 的 Web 工作台。基于 Next.js 16 + React 19 + Tailwind CSS 4。

> 这只是简短入口指引。完整指南：
> - **[../README_zh.md](../README_zh.md)** — 项目总览（中文）
> - **[CLAUDE.md](CLAUDE.md)** — 前端架构与开发指南
> - **[../CONTRIBUTING.md](../CONTRIBUTING.md)** — 贡献流程

## 技术栈

- **Next.js 16** + App Router
- **React 19** + **TypeScript 5.8**
- **Tailwind CSS 4**（`@import` 语法 + CSS 变量）
- **pnpm 10.26.2**（workspaces）
- **LangGraph SDK**（`@langchain/langgraph-sdk`）+ **TanStack Query**
- **Shadcn UI / MagicUI / React Bits / Vercel AI Elements**（注册表生成，`ui/`、`ai-elements/` 不要手改）

## 前置

- Node.js 22+
- pnpm 10.26.2+

## 命令

```bash
pnpm dev          # Turbopack dev，http://localhost:3000
pnpm build        # 生产构建（需要 BETTER_AUTH_SECRET）
pnpm lint         # ESLint
pnpm typecheck    # tsc --noEmit
pnpm format:write # Prettier 写盘
pnpm start        # 起生产 server
```

**注意**：
- `pnpm check` 是坏的，不要用，分开跑 `pnpm lint && pnpm typecheck`
- 没有测试框架，验证靠 lint + typecheck + 手动浏览器
- `pnpm build` 必须 `BETTER_AUTH_SECRET=...`，否则被 env 校验拒绝

## 路由

```
/                              # Forge Landing
/workspace/chats               # 会话列表
/workspace/chats/new           # 新会话
/workspace/chats/[thread_id]   # 单会话页（核心交互）
```

## 关键环境变量

`.env`（从 `.env.example` 复制）：

```bash
BETTER_AUTH_SECRET=local-dev-secret             # 必须，生产构建用
NEXT_PUBLIC_BACKEND_BASE_URL=                    # 可选，留空走 nginx :2026
NEXT_PUBLIC_LANGGRAPH_BASE_URL=                  # 可选，同上
```

`make dev` 从根目录跑时，前端自动通过 nginx 接到后端，无需设置。

## 目录入口

| 路径 | 职责 |
|---|---|
| `src/app/` | Next.js App Router 页面 |
| `src/components/workspace/welcome.tsx` | Forge Welcome / Hero / Action Cards |
| `src/core/threads/` | 线程创建、流、状态管理 |
| `src/core/api/` | LangGraph SDK 客户端单例 |
| `src/env.js` | env 校验 schema |

更多见 [CLAUDE.md](CLAUDE.md)。

## 协议

MIT License。详见 [LICENSE](../LICENSE)。
