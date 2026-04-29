# DeerFlow 前端界面描述文档

## 1. 技术栈概述

| 类别 | 技术 |
|------|------|
| 框架 | Next.js 16 + React 19 + TypeScript 5.8 |
| UI 组件库 | shadcn/ui (基于 Radix UI) |
| 样式方案 | Tailwind CSS 4 |
| 图标库 | Lucide React |
| AI SDK | Vercel AI SDK, @langchain/langgraph-sdk |
| 状态管理 | @tanstack/react-query |
| 动画 | motion, gsap, tw-animate-css |
| 主题 | next-themes (亮/暗模式) |

---

## 2. 页面结构

### 2.1 Landing 页面 (`/`)

全屏深色主题单页应用，以 `#0a10` 为背景。

```
┌─────────────────────────────────────────────────────┐
│  Header (固定导航，毛玻璃效果)                          │
├─────────────────────────────────────────────────────┤
│  Hero (全屏，使用鹿形mask的FlickeringGrid背景)         │
│  - WordRotate 循环展示能力关键词                       │
│  - "Get Started with 2.0" CTA 按钮                    │
├─────────────────────────────────────────────────────┤
│  CaseStudySection (3列网格卡片，hover上移动画)           │
├─────────────────────────────────────────────────────┤
│  SkillsSection (技能展示)                             │
├─────────────────────────────────────────────────────┤
│  SandboxSection (终端模拟器 + 打字机动画)               │
├─────────────────────────────────────────────────────┤
│  WhatsNewSection (最新动态)                           │
├─────────────────────────────────────────────────────┤
│  CommunitySection (社区)                              │
├─────────────────────────────────────────────────────┤
│  Footer (MIT许可证 + 版权)                            │
└─────────────────────────────────────────────────────┘
```

#### Header 设计
- 固定定位，高度 `h-16`
- 毛玻璃背景 (`backdrop-blur-xs`)
- 左侧: 品牌名 "DeerFlow" (衬线字体)
- 中间: Docs, Blog 导航链接
- 右侧: GitHub Star 按钮 (动态计数)

#### Hero 区域
- 全屏高度 `h-screen`
- `Galaxy` + `FlickeringGrid` 创造星空视觉效果
- SVG mask 技术形成鹿的轮廓
- 核心文案: "Deep Research with DeerFlow"

---

### 2.2 Workspace 页面 (`/workspace`)

#### 路由结构
```
/workspace                          → 重定向到新聊天或演示线程
/workspace/chats/[thread_id]        → 具体聊天页面
```

#### 整体布局
```
┌─────────────────────────────────────────────────────┐
│  WorkspaceHeader (面包屑 + GitHub链接)                │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│ Sidebar  │         ChatBox                           │
│ (可折叠)  │  ┌──────────────────────────────────┐   │
│          │  │     MessageList (对话列表)          │   │
│ - Nav    │  │                                    │   │
│ - Recent │  │                                    │   │
│ - Menu   │  ├──────────────────────────────────┤   │
│          │  │     InputBox (输入框)               │   │
│          │  └──────────────────────────────────┘   │
│          │                            │ Artifacts │ │
└──────────┴──────────────────────────────────────────┘
```

---

## 3. 组件体系

### 3.1 AI Elements 组件 (`/src/components/ai-elements/`)

| 组件 | 功能 |
|------|------|
| `message.tsx` | 基础消息组件 (Message, MessageContent, MessageActions, MessageToolbar) |
| `conversation.tsx` | 滚动容器，含空状态展示 |
| `prompt-input.tsx` | 输入框系统，支持拖拽上传、语音输入 |
| `reasoning.tsx` | 推理展示组件 |
| `chain-of-thought.tsx` | 思维链组件 |
| `code-block.tsx` | 代码块渲染 |
| `model-selector.tsx` | 模型选择器 |
| `suggestion.tsx` | 建议回复组件 |
| `task.tsx` | 任务组件 |
| `artifact.tsx` | 产物组件 |
| `context.tsx` | 上下文组件 |

### 3.2 Workspace 组件 (`/src/components/workspace/`)

| 组件 | 功能 |
|------|------|
| `workspace-container.tsx` | 页面容器 + Header |
| `workspace-sidebar.tsx` | 侧边栏包装 |
| `workspace-nav-menu.tsx` | 底部设置菜单 |
| `input-box.tsx` | 主输入框组件 |
| `recent-chat-list.tsx` | 历史聊天列表 |
| `chat-box.tsx` | 聊天+产物可调整面板 |
| `code-editor.tsx` | 代码编辑器 |
| `command-palette.tsx` | 命令面板 |
| `todo-list.tsx` | Todo 列表 |
| `token-usage-indicator.tsx` | Token 使用指示器 |

#### Workspace 子目录
```
workspace/
├── agents/        → Agent 相关组件
├── artifacts/     → Artifact 展示组件
├── chats/         → 聊天相关组件 (ChatBox)
├── citations/     → 引用组件
├── messages/      → 消息展示组件
└── settings/      → 设置组件
```

---

## 4. 消息系统

### 4.1 MessageList (`/src/components/workspace/messages/message-list.tsx`)
- 基于 `use-stick-to-bottom` 库实现自动滚动
- 消息分组:
  - `human` / `assistant` → `MessageListItem`
  - `assistant:clarification` → 直接显示 Markdown
  - `assistant:present-files` → 文件列表
  - `assistant:subagent` → `SubtaskCard`

### 4.2 MessageGroup (`/src/components/workspace/messages/message-group.tsx`)
- 显示 AI 思维链 (Chain of Thought)
- 折叠/展开推理过程
- 工具调用展示 (web_search, image_search, write_file, bash 等)

### 4.3 消息附件
- `RichFilesList`: 文件卡片网格
- `RichFileCard`: 单个文件卡片
  - 图片预览
  - 文件类型 Badge
  - 文件大小
  - 上传中状态 (旋转 loading)

---

## 5. 输入框系统

### 5.1 InputBox (`/src/components/workspace/input-box.tsx`)

多模式 AI 交互系统:

| 模式 | 说明 |
|------|------|
| Flash | 最快响应，无思考 |
| Thinking | 低推理投入 |
| Pro | 中等推理投入 |
| Ultra | 高推理投入 (金色文字特效) |

#### 核心功能
- 文件上传附件 (`PromptInputAttachments`)
- 模型选择器 (`ModelSelector`)
- 模式切换下拉菜单
- 推理投入级别选择
- 建议回复 (Followups) - 流式获取
- 确认对话框 (输入框有内容时)

#### 快捷键
- `Enter` 提交
- `Shift+Enter` 换行
- `Backspace` 在空输入时删除附件

### 5.2 PromptInput (`/src/components/ai-elements/prompt-input.tsx`)
- 全局拖拽上传 (`globalDrop`)
- 文件验证 (maxFiles, maxFileSize, accept)
- `PromptInputProvider` 外部状态管理
- 语音输入 (`PromptInputSpeechButton`)
- 附件预览 HoverCard

---

## 6. 侧边栏设计

### 6.1 WorkspaceSidebar
- 基于 shadcn/ui Sidebar 组件
- 可折叠 (`collapsible="icon"`)

```
┌─────────────────┐
│  WorkspaceHeader │ ← SidebarHeader
├─────────────────┤
│  WorkspaceNavChat │ ← SidebarContent
│  RecentChatList  │
├─────────────────┤
│  WorkspaceNavMenu │ ← SidebarFooter
└─────────────────┘
```

### 6.2 RecentChatList
每个聊天项支持:
- 重命名 (Pencil 图标 → Dialog)
- 分享 (Share2 → 复制链接)
- 导出 (Download → Markdown/JSON)
- 删除 (Trash2)

### 6.3 WorkspaceNavMenu
底部菜单: Settings, Official Website, GitHub, Report Issue, Contact Us, About

---

## 7. 主题配色

### 7.1 亮色模式 (`:root`)
```css
--background: oklch(0.9855 0.0098 87.47)   /* 近白色 */
--foreground: oklch(0.145 0 0)             /* 深灰文字 */
--primary: oklch(0 0 0)                    /* 纯黑 */
--secondary: oklch(0.9455 0.0098 87.47)    /* 浅灰背景 */
--muted: oklch(0.97 0.0098 87.47)         /* 柔和背景 */
--accent: oklch(0.94 0.0098 87.47)        /* 强调色 */
--border: oklch(0.922 0.0098 87.47)       /* 边框 */
--destructive: oklch(0.577 0.245 27.325)   /* 红色警告 */
```

### 7.2 暗色模式 (`.dark`)
```css
--background: oklch(0.24 0.0036 106.64)   /* 深蓝黑 */
--foreground: oklch(0.985 0 0)            /* 白色文字 */
--primary: oklch(1 0 0)                    /* 白色 */
--secondary: oklch(0.3 0.0036 106.64)     /* 深蓝灰 */
--muted: oklch(0.269 0.0036 106.64)       /* 更深蓝灰 */
--accent: oklch(0.32 0.0036 106.64)       /* 蓝灰强调 */
--destructive: oklch(0.704 0.191 22.216)   /* 红色 */
```

### 7.3 特殊效果
- **Golden Text**: 金色渐变 (`linear-gradient(135deg, #d19e1d 0%, #e9c665 50%, #e3a812 100%)`)
- **Ambilight**: 彩虹渐变动画边框
- **Aurora Text**: 极光彩色文字动画

---

## 8. 关键交互设计

### 8.1 欢迎界面 (Welcome)
- 根据 URL `?mode=skill` 显示不同文案
- Ultra 模式金色渐变文字
- 挥手动画效果

### 8.2 聊天消息流
- LangGraph SDK 流式传输
- `StreamingIndicator` 加载状态
- 消息分组折叠/展开

### 8.3 Artifact 系统
- 可调整大小的侧边面板
- 文件列表 → 点击查看详情
- 代码编辑器内联编辑

### 8.4 ChatBox 布局
- 使用 `ResizablePanelGroup` 实现
- 默认: `chat: 100, artifacts: 0`
- 打开产物: `chat: 60, artifacts: 40`

---

## 9. 目录结构

```
frontend/
├── src/
│   ├── app/
│   │   ├── [lang]/              # 国际化路由 (en-US, zh-CN)
│   │   │   └── docs/            # 文档页面
│   │   ├── api/                 # API 路由 (auth, memory)
│   │   ├── mock/                # Mock API
│   │   ├── workspace/           # Workspace 应用
│   │   │   ├── chats/           # 聊天路由
│   │   │   └── page.tsx         # 主聊天页
│   │   ├── layout.tsx           # 根布局
│   │   └── page.tsx             # Landing 页
│   ├── components/
│   │   ├── ui/                  # shadcn/ui 基础组件
│   │   ├── ai-elements/         # AI SDK 组件
│   │   ├── landing/             # Landing 页组件
│   │   └── workspace/           # Workspace 组件
│   ├── core/                    # 业务逻辑
│   │   ├── agents/              # Agent API 和 hooks
│   │   ├── api/                 # LangGraph API 客户端
│   │   ├── artifacts/           # Artifact 加载/缓存
│   │   ├── config/              # 配置
│   │   ├── i18n/                # 国际化
│   │   ├── mcp/                 # Model Context Protocol
│   │   ├── memory/              # 记忆系统
│   │   ├── messages/            # 消息处理
│   │   ├── models/              # TypeScript 类型
│   │   ├── settings/            # 用户偏好
│   │   ├── skills/              # Skills 管理
│   │   ├── threads/             # 线程管理
│   │   ├── todos/               # Todo 管理
│   │   └── tools/               # 工具函数
│   ├── hooks/                   # 共享 React hooks
│   ├── lib/                     # 工具函数 (cn(), IME)
│   ├── server/                  # 服务端代码 (better-auth)
│   ├── styles/                  # 全局样式
│   ├── content/                 # MDX 内容
│   └── typings/                 # 类型定义
├── public/                      # 静态资源
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── next.config.js
```

---

## 10. 设计特点总结

1. **深色主题为主** - 接近 VS Code/Linear 的美学
2. **组件高度拆分** - 大量使用 shadcn/ui 原子组件
3. **多模式 AI 交互** - Flash/Thinking/Pro/Ultra 适应不同任务
4. **丰富流式反馈** - 思维链、工具调用、上传进度
5. **产物中心设计** - 文件/代码作为一等公民展示
6. **响应式布局** - 侧边栏可折叠，聊天/产物面板可调整
7. **渐变与动画** - Golden Text、Ambilight、Aurora 等特效
