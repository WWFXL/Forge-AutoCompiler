# frontend/CLAUDE.md

本文件是 Forge-AutoCompiler 前端的工作指南。**先读根目录的 [`/CLAUDE.md`](../CLAUDE.md)**，了解整体定位与编译核心。本文件聚焦前端。

## 1. 角色与现状

前端是 Forge-AutoCompiler 的 Web 工作台。用户在浏览器里：

- 看 Forge Landing（`src/app/page.tsx`）
- 创建会话（thread），通过聊天界面把编译任务（"克隆并编译 https://..."）交给 Lead Agent
- 实时看 agent 工具调用与 streaming 输出
- 查看产物（artifacts）和 todos

**当前现状**：UI 沿用 DeerFlow 时代的通用对话式工作台。Welcome 区已经换成 Forge 主题（金色，三张 action card 直接预填 CMake / gRPC / 架构介绍三个示例任务），但**没有专门的「编译表单」**。用户仍然以自然语言驱动 agent。

技术栈：

- **Next.js 16**（App Router）+ **React 19** + **TypeScript 5.8**
- **Tailwind CSS 4**（`@import` 语法 + CSS variables 主题）
- **pnpm 10.26.2**（workspaces；`packageManager` 字段锁死）
- **LangGraph SDK** (`@langchain/langgraph-sdk`)：与后端 LangGraph Server 之间的流协议
- **TanStack Query**：服务端状态
- **Shadcn UI / MagicUI / React Bits / Vercel AI Elements**：UI 原子（`components/ui/`、`components/ai-elements/` 自动生成，**不要手改**）

## 2. 路由

```
/                              # Forge Landing（Welcome + Hero + 工具栏）
/workspace/chats               # 会话列表
/workspace/chats/new           # 新会话
/workspace/chats/[thread_id]   # 单个会话（核心交互页）
```

`page.tsx` 在 `src/app/` 下按上述结构组织。Server Component 为默认，需要交互的组件加 `"use client"`。

## 3. 目录布局

```
src/
├── app/                    # Next.js App Router 页面
│   ├── workspace/          # 工作台路由
│   └── api/                # Next.js API routes（少量）
├── components/
│   ├── ui/                 # Shadcn 原子（自动生成，ESLint 忽略）
│   ├── ai-elements/        # Vercel AI Elements（自动生成，ESLint 忽略）
│   ├── landing/            # Landing 页区块
│   └── workspace/          # 工作台组件，包含 welcome.tsx（Forge Hero + Action Cards）
├── core/                   # 业务逻辑（前端的"backend"）
│   ├── threads/            # 线程创建、流、状态管理（hooks + types）
│   ├── api/                # LangGraph SDK 客户端单例
│   ├── artifacts/          # 产物加载与缓存
│   ├── messages/           # 消息处理与变换
│   ├── i18n/               # 国际化（en-US, zh-CN）
│   ├── settings/           # localStorage 偏好
│   ├── skills/             # Skills 安装与管理（非编译核心）
│   ├── mcp/                # MCP 集成（非编译核心）
│   ├── memory/             # 记忆系统（非编译核心）
│   └── models/             # 类型与模型
├── hooks/                  # 共享 React hooks
├── lib/                    # 工具（cn() = clsx + tailwind-merge）
├── server/                 # 服务端代码（better-auth，尚未启用）
├── env.js                  # @t3-oss/env-nextjs + Zod 校验
└── styles/                 # 全局 CSS（Tailwind v4 + CSS 变量）
```

## 4. 数据流

```
用户输入 → core/threads/hooks.ts（useSubmitThread / useThreadStream）
        → LangGraph SDK（getAPIClient()）→ /api/langgraph/* → LangGraph Server
        → 流回事件（messages-tuple / values / end）
        → thread state（messages / artifacts / todos）
        → 组件订阅渲染
```

关键约定：
- **Thread hooks 是唯一的对外 API**（`useThreadStream`、`useSubmitThread`、`useThreads`）
- **LangGraph 客户端是单例**（`getAPIClient()`，`core/api/`）
- **Server Components 优先**；只在交互必需时 `"use client"`

## 5. Forge 视觉与文案

- 入口文案 `src/components/workspace/welcome.tsx`：标题用 AuroraText，金色配色（`#efefbb` / `#e9c665` / `#e3a812`）
- 三张 Action Card：
  1. "探索 Forge 工作流"：触发架构介绍提问
  2. CMake 编译示例：`https://github.com/fmtlib/fmt`
  3. gRPC 含子模块编译示例：`https://github.com/grpc/grpc`
- 配色变量在 `src/styles/`（`forge-gold` / `forge-bg` / `forge-card` 等 CSS class）

改文案时同步改 i18n（`core/i18n/en-US.ts` / `zh-CN.ts`），Welcome 组件用 `useI18n()` 拿 `t.welcome.actionCards.*`。

## 6. 命令

```bash
pnpm dev         # Turbopack dev server，http://localhost:3000
pnpm build       # 生产构建
pnpm lint        # ESLint
pnpm lint:fix    # ESLint --fix
pnpm typecheck   # tsc --noEmit
pnpm format      # Prettier 检查
pnpm format:write # Prettier 写盘
pnpm start       # 起生产 server
```

**没有测试框架**。前端验证靠 `pnpm lint && pnpm typecheck` + 手动浏览器测。

## 7. 已知坑

- **`pnpm check` 是坏的**——`next lint` 在当前 Next.js 16 配置下解析到错误目录。**不要用 `pnpm check`**，分开跑 `pnpm lint && pnpm typecheck`。
- **`pnpm build` 必须设 `BETTER_AUTH_SECRET`**——`src/env.js` 用 `@t3-oss/env-nextjs + Zod` 在生产构建时强校验。命令示例：`BETTER_AUTH_SECRET=local-dev-secret pnpm build`。`SKIP_ENV_VALIDATION=1` 能压住校验但 Better Auth 仍可能告警。
- **proxy 环境变量会静默破坏 `pnpm install`**——拉依赖失败时先 `unset http_proxy https_proxy`。
- **后端 URL 默认走 nginx**：`NEXT_PUBLIC_BACKEND_BASE_URL` 与 `NEXT_PUBLIC_LANGGRAPH_BASE_URL` 留空时由 nginx（端口 2026）转发。直连本地后端时才需要设置。

## 8. 与后端的契约

- **流协议**：`@langchain/langgraph-sdk` 的 SSE。前端订阅 `messages-tuple` 收增量消息、`values` 收 ThreadState 快照、`end` 表示流结束
- **artifacts**：通过 Gateway 的 `GET /api/threads/{id}/artifacts/{path}` 拿，前端有同名 hook（`useArtifact`）
- **uploads**：`POST /api/threads/{id}/uploads`（multipart），Gateway 会自动把 PDF/PPT/Excel/Word 转 Markdown
- **suggestions**：`POST /api/threads/{id}/suggestions` 生成后续追问

UI 主调用入口都封装在 `core/api/`、`core/threads/`、`core/artifacts/`、`core/skills/`、`core/mcp/`、`core/memory/`。

## 9. 代码风格

- **import 排序**：builtin → external → internal → parent → sibling，字母序，组间空行。`import { type Foo }` 内联类型。
- **未用变量**前缀 `_`
- **className 合并**用 `cn()`（`@/lib/utils`）
- **路径别名** `@/*` → `src/*`
- **`ui/` 与 `ai-elements/` 是注册表生成的（Shadcn / MagicUI / React Bits / Vercel AI Elements），不手改**

## 10. 项目状态快照

按根目录 [`/CLAUDE.md` §7](../CLAUDE.md#7-项目状态快照强制) 维护 `<repo-root>/.claude/memory/project.md`。回复结尾必须有 `[snapshot:done]` 或 `[snapshot:noop]`。
