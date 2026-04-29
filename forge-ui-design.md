# Forge UI 设计文档

本文档用于精确复原 Forge 前端界面的所有页面和组件。

---

## 目录

1. [全局设计系统](#1-全局设计系统)
2. [Landing 页面](#2-landing-页面)
3. [Workspace 页面](#3-workspace-页面)
4. [组件库](#4-组件库)

---

## 1. 全局设计系统

### 3.1 颜色变量 (CSS Variables)

#### 亮色模式 (`:root`)

```css
:root {
  /* 圆角 */
  --radius: 0.625rem;        /* 10px */

  /* 背景 & 文字 */
  --background: oklch(0.9855 0.0098 87.47);      /* #fafafa 近白色 */
  --foreground: oklch(0.145 0 0);                /* #1a1a1a 深灰色 */

  /* 卡片 */
  --card: oklch(1 0.0098 87.47);
  --card-foreground: oklch(0.145 0 0);

  /* 弹出层 */
  --popover: oklch(1 0.0098 87.47);
  --popover-foreground: oklch(0.145 0 0);

  /* 主色 */
  --primary: oklch(0 0 0);                        /* #000000 纯黑 */
  --primary-foreground: oklch(0.985 0 0);         /* #ffffff 白色 */

  /* 次要色 */
  --secondary: oklch(0.9455 0.0098 87.47);
  --secondary-foreground: oklch(0.205 0 0);

  /* 柔和色 */
  --muted: oklch(0.97 0.0098 87.47);
  --muted-foreground: oklch(0.556 0 0);

  /* 强调色 */
  --accent: oklch(0.94 0.0098 87.47);
  --accent-foreground: oklch(0.205 0 0);

  /* 危险/破坏性操作 */
  --destructive: oklch(0.577 0.245 27.325);        /* 红色 */

  /* 边框 & 输入 */
  --border: oklch(0.922 0.0098 87.47);
  --input: oklch(0.88 0.0098 87.47);
  --ring: transparent;

  /* 图表颜色 */
  --chart-1: oklch(0.646 0.222 41.116);
  --chart-2: oklch(0.6 0.118 184.704);
  --chart-3: oklch(0.398 0.07 227.392);
  --chart-4: oklch(0.828 0.189 84.429);
  --chart-5: oklch(0.769 0.188 70.08);
}
```

#### 暗色模式 (`.dark`)

```css
.dark {
  /* 背景 & 文字 */
  --background: oklch(0.24 0.0036 106.64);        /* #0a0a0a 深蓝黑 */
  --foreground: oklch(0.985 0 0);                 /* #ffffff 白色 */

  /* 卡片 */
  --card: oklch(0.238 0.0036 106.64);
  --card-foreground: oklch(0.985 0 0);

  /* 弹出层 */
  --popover: oklch(0.205 0.0036 106.64);
  --popover-foreground: oklch(0.985 0 0);

  /* 主色 */
  --primary: oklch(1 0 0);                        /* #ffffff 白色 */
  --primary-foreground: oklch(0.205 0 0);

  /* 次要色 */
  --secondary: oklch(0.3 0.0036 106.64);
  --secondary-foreground: oklch(0.985 0 0);

  /* 柔和色 */
  --muted: oklch(0.269 0.0036 106.64);
  --muted-foreground: oklch(0.708 0 0);

  /* 强调色 */
  --accent: oklch(0.32 0.0036 106.64);
  --accent-foreground: oklch(0.985 0 0);

  /* 危险/破坏性操作 */
  --destructive: oklch(0.704 0.191 22.216);       /* 红色 */

  /* 边框 & 输入 */
  --border: oklch(1 0 0 / 10%);                   /* 10% 白色 */
  --input: oklch(1 0 0 / 15%);                   /* 15% 白色 */
  --ring: transparent;

  /* 图表颜色 */
  --chart-1: oklch(0.488 0.243 264.376);
  --chart-2: oklch(0.696 0.17 162.48);
  --chart-3: oklch(0.769 0.188 70.08);
  --chart-4: oklch(0.627 0.265 303.9);
  --chart-5: oklch(0.645 0.246 16.439);
}
```

#### Sidebar 专用颜色

```css
/* 亮色模式 */
--sidebar: oklch(0.965 0.0098 87.47);
--sidebar-foreground: oklch(0.145 0 0);
--sidebar-primary: oklch(0.205 0.0098 87.47);
--sidebar-primary-foreground: oklch(0.985 0 0);
--sidebar-accent: oklch(0.925 0.0098 87.47);
--sidebar-accent-foreground: oklch(0.205 0 0);
--sidebar-border: oklch(0.922 0.0098 87.47);
--sidebar-ring: oklch(0.708 0 0);

/* 暗色模式 */
--sidebar: oklch(0.245 0.0036 106.64);
--sidebar-foreground: oklch(0.985 0 0);
--sidebar-primary: oklch(0.488 0.243 264.376);
--sidebar-primary-foreground: oklch(0.985 0 0);
--sidebar-accent: oklch(0.29 0.0036 106.64);
--sidebar-accent-foreground: oklch(0.985 0 0);
--sidebar-border: oklch(1 0 0 / 10%);
--sidebar-ring: oklch(0.556 0 0);
```

### 3.2 圆角系统

```css
--radius: 0.625rem;         /* 10px - 基础圆角 */

--radius-sm: calc(var(--radius) - 4px);   /* 6px */
--radius-md: calc(var(--radius) - 2px);   /* 8px */
--radius-lg: var(--radius);                 /* 10px */
--radius-xl: calc(var(--radius) + 4px);   /* 14px */
--radius-2xl: calc(var(--radius) + 8px);  /* 18px */
--radius-3xl: calc(var(--radius) + 12px); /* 22px */
--radius-4xl: calc(var(--radius) + 16px); /* 26px */
```

### 3.3 字体

```css
--font-sans: ui-sans-serif, system-ui, sans-serif,
    "Apple Color Emoji", "Segoe UI Emoji",
    "Segoe UI Symbol", "Noto Color Emoji";
```

### 3.4 容器宽度

```css
--container-width-xs: calc(var(--spacing) * 72);
--container-width-sm: calc(var(--spacing) * 144);
--container-width-md: calc(var(--spacing) * 204);
--container-width-lg: calc(var(--spacing) * 256);
```

### 3.5 动画

| 动画名 | 时长 | 效果 |
|--------|------|------|
| `fade-in` | 1.1s | 淡入 |
| `fade-in-up` | 0.15s | 从下往上淡入 |
| `bouncing` | 0.5s | 上下弹跳，循环 |
| `skeleton-entrance` | 0.35s | 骨架屏入场 |
| `suggestion-in` | 0.2s | 建议条目从顶部滑入 |
| `wave` | 0.6s | 挥手动画 |
| `aurora` | 8s | 极光效果 |
| `shine` | - | 闪光效果 |
| `ambilight` | 40s | 彩虹光晕效果 |

### 3.6 特殊效果

```css
/* 金色文字渐变 (Ultra模式) */
background: linear-gradient(135deg, #d19e1d 0%, #e9c665 50%, #e3a812 100%);
```

---

## 2. Landing 页面

### 2.1 Header 导航栏

**文件**: `src/components/landing/header.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│  Forge          Docs  Blog                    [⭐ Star on GitHub] │
│  ────────────────────────────────────────────────────────────────  │ ← 1px 渐变线
└────────────────────────────────────────────────────────────────────┘
```

**尺寸**:
- 高度: `h-16` (64px)
- 固定定位: `fixed top-0 right-0 left-0`
- z-index: `z-20`

**布局**: Flexbox, `items-center justify-between`

**背景**:
- `backdrop-blur-xs` 毛玻璃效果
- GitHub按钮后方有粉色→紫色渐变光晕:
  ```css
  background: linear-gradient(90deg, #ff80b5 0%, #9089fc 100%);
  filter: blur(16px);
  opacity: 0.3;
  ```

**间距**:
- Logo区域: `flex items-center gap-6`
- 导航链接: `mr-8 ml-auto flex items-center gap-8 text-sm font-medium`

**底部边框线**:
```css
hr: from-border/0 via-border/70 to-border/0
height: 1px
position: absolute top-16 right-0 left-0
```

**GitHub按钮**:
```tsx
<Button variant="outline" size="sm">
  <GitHubLogoIcon className="size-4" />
  Star on GitHub
  {hasToken && <StarCounter />}
</Button>
```

---

### 2.2 Hero 区域

**文件**: `src/components/landing/hero.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│                                                                    │
│                     [WordRotate Animation]                         │
│                        with Forge                                  │
│                                                                    │
│              An open-source SuperAgent harness...                   │
│                                                                    │
│                    [ Get Started ]  →                              │
│                                                                    │
│  ════════════════════════════════════════════════════════════════  │ ← FlickeringGrid
│  ════════════════════════════════════════════════════════════════  │ ← Galaxy (星场)
│  ════════════════════════════════════════════════════════════════  │
└────────────────────────────────────────────────────────────────────┘
```

**尺寸**: 全屏 `h-screen`

**背景层 (z-0, absolutely positioned)**:

1. **Galaxy (星场)**:
   - 黑色遮罩: `bg-black/40`
   - 参数:
     - `mouseRepulsion={false}`
     - `starSpeed={0.2}`
     - `density={0.6}`
     - `glowIntensity={0.35}`
     - `twinkleIntensity={0.3}`
     - `speed={0.5}`

2. **FlickeringGrid (闪烁网格)**:
   ```tsx
   <FlickeringGrid
     className="absolute inset-0 z-0 translate-y-8"
     squareSize={4}
     gridGap={4}
     color="white"
     maxOpacity={0.3}
     flickerChance={0.25}
   />
   ```

**内容区域**:
```tsx
<div className="container-md relative z-10 mx-auto flex h-screen flex-col items-center justify-center">
  <h1 className="flex items-center gap-2 text-4xl font-bold md:text-6xl">
    <WordRotate words={[...13个单词]} />
    <div>with Forge</div>
  </h1>

  <p className="text-muted-foreground mt-8 scale-105 text-center text-2xl text-shadow-sm">
    An open-source SuperAgent harness that researches, codes, and creates...
  </p>

  <Link href="/workspace">
    <Button className="size-lg mt-8 scale-108" size="lg">
      Get Started
      <ChevronRightIcon className="size-4" />
    </Button>
  </Link>
</div>
```

**WordRotate 单词列表**:
```js
[
  "Deep Research",
  "Collect Data",
  "Analyze Data",
  "Generate Webpages",
  "Vibe Coding",
  "Generate Slides",
  "Generate Images",
  "Generate Podcasts",
  "Generate Videos",
  "Generate Songs",
  "Organize Emails",
  "Do Anything",
  "Learn Anything"
]
```

---

### 2.3 CaseStudySection 案例研究区

**文件**: `src/components/landing/sections/case-study-section.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│                         Case Studies                                │
│                   See how Forge is used in the wild                │
├────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │             │  │             │  │             │                │
│  │   [图片]    │  │   [图片]    │  │   [图片]    │                │
│  │             │  │             │  │             │                │
│  │─────────────│  │─────────────│  │─────────────│                │
│  │   标题      │  │   标题      │  │   标题      │                │
│  │   描述...   │  │   描述...   │  │   描述...   │                │
│  └─────────────┘  └─────────────┘  └─────────────┘                │
│       ↖ hover: 卡片上移，内容展开                                   │
└────────────────────────────────────────────────────────────────────┘
```

**布局**:
- 网格: `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4`
- 容器: `container-md mt-8 px-4`

**卡片结构**:
```tsx
<Card className="group/card relative h-64 overflow-hidden">
  {/* 背景图片 */}
  <div
    className="absolute inset-0 z-0 bg-cover bg-center bg-no-repeat
               transition-all duration-300
               group-hover/card:scale-110 group-hover/card:brightness-90"
    style={{ backgroundImage: `url(/images/${threadId}.jpg)` }}
  />

  {/* 内容区域 - 默认显示底部60px */}
  <div className="flex h-full w-full translate-y-[calc(100%-60px)] flex-col items-center
                  transition-all duration-300
                  group-hover/card:translate-y-[calc(100%-128px)]">
    {/* 渐变遮罩 */}
    <div className="w-full p-4" style={{
      background: "linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 100%)"
    }}>
      <h3 className="flex h-14 items-center text-xl font-bold">标题</h3>
      <p className="text-sm text-white/85">描述文字</p>
    </div>
  </div>
</Card>
```

**卡片尺寸**: `h-64` (256px)

---

### 2.4 SkillsSection 技能展示区

**文件**: `src/components/landing/sections/skills-section.tsx`

**尺寸**: 全屏高度 `h-[calc(100vh-64px)]`

**背景**: `bg-white/2`

**内容**: `ProgressiveSkillsAnimation` 组件

---

### 2.5 ProgressiveSkillsAnimation 技能动画

**文件**: `src/components/landing/progressive-skills-animation.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  ┌──────────────────────────┐   ┌──────────────────────────────┐  │
│  │  📁 src/                 │   │  ● Forge Agent              │  │
│  │    📄 index.html        │   │                              │  │
│  │    📄 style.css          │   │  > Research mRNA...         │  │
│  │    📄 app.js            │   │                              │  │
│  │    📄 config.json        │   │  ✓ scanning                 │  │
│  │    📄 README.md         │   │  ✓ load-skill               │  │
│  │                         │   │  ✓ load-template            │  │
│  │                         │   │  ✓ researching              │  │
│  │                         │   │  ✓ load-frontend            │  │
│  │                         │   │  ✓ building                 │  │
│  │                         │   │  ✓ deploy                   │  │
│  │                         │   │  ✓ done                     │  │
│  │                         │   │                              │  │
│  │                         │   │  ┌────────────────────────┐  │  │
│  │                         │   │  │ Ask Forge anything... │  │  │
│  │                         │   │  └────────────────────────┘  │  │
│  └──────────────────────────┘   └──────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**容器尺寸**: `h-[calc(100vh-280px)]`

**布局**: Flex row, 两栏各占 50%

**左栏 - 文件树**:
```tsx
<div className="flex flex-1 flex-col">
  <p className="mb-4 font-mono text-sm text-zinc-500">src/</p>
  <div className="space-y-2">
    {files.map((file, i) => (
      <div
        key={file.name}
        className={`flex items-center gap-2 transition-all duration-300 ${
          activeIndex > i ? 'translate-x-8 scale-105 text-blue-400' : ''
        } ${activeIndex === i ? 'text-white' : 'text-zinc-600'}`}
        style={{ paddingLeft: `${file.indent * 24}px` }}
      >
        <FileIcon className="size-4" />
        <span>{file.name}</span>
      </div>
    ))}
  </div>
</div>
```

**右栏 - 聊天界面**:
```tsx
<div className="flex flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50">
  {/* 聊天头部 */}
  <div className="border-b border-zinc-800 p-4">
    <div className="flex items-center gap-2">
      <div className="h-3 w-3 rounded-full bg-green-500" />
      <span className="text-sm text-zinc-400">Forge Agent</span>
    </div>
  </div>

  {/* 聊天消息 */}
  <div className="flex-1 space-y-4 overflow-y-auto p-6">
    {/* 动画状态列表 */}
    {phases.slice(0, phaseIndex + 1).map((phase, i) => (
      <div key={i} className="flex items-center gap-2">
        {phase === 'done' ? (
          <CheckCircleIcon className="size-4 text-green-500" />
        ) : (
          <div className="h-3 w-3 rounded-full bg-blue-500 animate-pulse" />
        )}
        <span className={phase === 'done' ? 'text-green-500' : 'text-white'}>
          {phase}
        </span>
      </div>
    ))}
  </div>

  {/* 输入框 (装饰性) */}
  <div className="border-t border-zinc-800 p-4">
    <div className="rounded-xl bg-zinc-800 px-4 py-3 text-sm text-zinc-500">
      Ask Forge anything...
    </div>
  </div>
</div>
```

---

### 2.6 SandboxSection 沙箱区

**文件**: `src/components/landing/sections/sandbox-section.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│                      Agent Runtime Environment                       │
│                                                                    │
│  ┌──────────────────────────────┐   OPEN-SOURCE                   │
│  │  $ cat requirements.txt      │                                 │
│  │  pygame==2.5.0               │   AIO Sandbox                    │
│  │                              │                                 │
│  │  $ pip install -r ...        │   All-in-One Sandbox            │
│  │  ✔ Installed pygame          │   combines Browser, Shell,       │
│  │                              │   File, MCP and VSCode Server    │
│  │  $ write game.py --lines 156 │                                 │
│  │  ✔ Written 156 lines         │   ┌─────┐ ┌─────┐ ┌─────┐      │
│  │                              │   │Isold│ │ Safe│ │Persist│     │
│  │  $ python game.py --test     │   └─────┘ └─────┘ └─────┘      │
│  │  ✔ All sprites loaded        │   ┌─────┐ ┌─────┐              │
│  │  ✔ Physics engine OK         │   │Mount│ │ Long│              │
│  └──────────────────────────────┘   │able │ │ run │              │
│                                    └─────┘ └─────┘              │
└────────────────────────────────────────────────────────────────────┘
```

**布局**: Flex row (lg), `gap-12 lg:gap-16`

**Terminal 尺寸**: `h-[360px] w-full`

**终端内容**:
```tsx
<Terminal className="h-[360px] w-full">
  <TypingAnimation>$ cat requirements.txt</TypingAnimation>
  <AnimatedSpan delay={800} className="text-zinc-400">
    pygame==2.5.0
  </AnimatedSpan>
  {/* ... 更多内容 */}
</Terminal>
```

**特性标签**:
```tsx
<span className="rounded-full border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm text-zinc-300">
  Isolated
</span>
```

---

### 2.7 WhatsNewSection 最新动态

**文件**: `src/components/landing/sections/whats-new-section.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│                        Whats New in Forge                          │
│                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ Context Eng...  │  │ Long Task Run...│  │ Extensible      │     │
│  │ Long/Short-term │  │ Planning and    │  │ Skills and      │     │
│  │ Memory          │  │ Sub-tasking     │  │ Tools           │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ Persistent      │  │ Flexible        │  │ Free            │     │
│  │ Sandbox with    │  │ Multi-Model     │  │ Open Source     │     │
│  │ File System     │  │ Support         │  │                 │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
└────────────────────────────────────────────────────────────────────┘
```

**使用组件**: `MagicBento` (6个BentoCard)

**卡片数据**:
```tsx
const features = [
  { color: "#0a0a0a", label: "Context Engineering", title: "Long/Short-term Memory" },
  { color: "#0a0a0a", label: "Long Task Running", title: "Planning and Sub-tasking" },
  { color: "#0a0a0a", label: "Extensible", title: "Skills and Tools" },
  { color: "#0a0a0a", label: "Persistent", title: "Sandbox with File System" },
  { color: "#0a0a0a", label: "Flexible", title: "Multi-Model Support" },
  { color: "#0a0a0a", label: "Free", title: "Open Source" },
];
```

---

### 2.8 CommunitySection 社区区

**文件**: `src/components/landing/sections/community-section.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│                    ✨ Join the Community ✨                         │
│                                                                    │
│        Contribute brilliant ideas to shape the future of Forge.    │
│                                                                    │
│                    [ Contribute Now ]                               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**标题**: `AuroraText` 组件，极光渐变动画
```tsx
<AuroraText colors={["#60A5FA", "#A5FA60", "#A560FA"]}>
  Join the Community
</AuroraText>
```

---

### 2.9 Footer 页脚

**文件**: `src/components/landing/footer.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│  ─────────────────────────────────────────────────────────────────  │
│                                                                    │
│         "Originated from Open Source, give back to Open Source."  │
│                                                                    │
│              Licensed under MIT License                             │
│              © 2026 Forge                                          │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**布局**: Flex column, `items-center justify-center`

**间距**: `mt-32` 顶部外边距

**分隔线**: 渐变 `from-border/0 via-white/20 to-border/0`

---

## 3. Workspace 页面

### 3.1 WorkspaceContainer 页面容器

**文件**: `src/components/workspace/workspace-container.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│  Workspace / chats / [thread_id]        [GitHub Icon]              │ ← Header h-16
├─────────┬──────────────────────────────────────────────────────────┤
│         │                                                          │
│ Sidebar │                    ChatBox                               │
│ (可折叠)│                                                          │
│         │  ┌────────────────────────────────────────────────────┐  │
│ [New]   │  │                                                    │  │
│         │  │              MessageList                           │  │
│ Recent  │  │                                                    │  │
│ Chats   │  │                                                    │  │
│         │  │                                                    │  │
│         │  ├────────────────────────────────────────────────────┤  │
│         │  │                    InputBox                        │  │
│         │  └────────────────────────────────────────────────────┘  │
│         │                                    │ Artifacts │         │
└─────────┴──────────────────────────────────────────────────────────┘
```

**Container className**:
```tsx
"flex h-screen w-full flex-col"
```

**Header className** (来自 workspace-container.tsx):
```tsx
"top-0 right-0 left-0 z-20 flex h-16 shrink-0 items-center justify-between
 gap-2 border-b backdrop-blur-sm transition-[width,height] ease-out
 group-has-data-[collapsible=icon]/sidebar-wrapper:h-12"
```

**Body className**:
```tsx
"relative flex min-h-0 w-full flex-1 flex-col items-center"
```

---

### 3.2 WorkspaceHeader (Sidebar内)

**文件**: `src/components/workspace/workspace-header.tsx`

**展开状态**:
```
┌──────────────────────────────────────┐
│  Forge                    [≡]       │ ← h-12
└──────────────────────────────────────┘
  ml-2                              pr-4
```

**折叠状态**:
```
┌────┐
│ DF │ ← 折叠时显示缩写
└────┘
```

**className 列表**:
```tsx
// 外层
"group/workspace-header flex h-12 flex-col justify-center"

// 展开状态
"flex items-center justify-between gap-2"

// 折叠状态
"group-has-data-[collapsible=icon]/sidebar-wrapper:-translate-y
 flex w-full cursor-pointer items-center justify-center"

// Logo文字
"text-primary ml-2 font-sans text-xl"

// 折叠时Logo
"text-primary block pt-1 font-sans
 group-hover/workspace-header:hidden"

// SidebarTrigger (折叠时hover显示)
"hidden pl-2 group-hover/workspace-header:block"
```

---

### 3.3 WorkspaceSidebar 侧边栏

**文件**: `src/components/workspace/workspace-sidebar.tsx`

**尺寸变量**:
```css
--sidebar-width: 16rem;        /* 展开宽度 256px */
--sidebar-width-icon: 3rem;     /* 折叠宽度 48px */
--sidebar-width-mobile: 18rem;  /* 移动端宽度 288px */
```

**布局结构**:
```
Sidebar (collapsible="icon")
├── SidebarHeader
│   └── WorkspaceHeader
│       ├── Logo + SidebarTrigger
│       └── SidebarMenu (New Chat)
├── SidebarContent
│   ├── WorkspaceNavChatList
│   └── RecentChatList (仅展开时显示)
├── SidebarFooter
│   └── WorkspaceNavMenu
└── SidebarRail (折叠按钮)
```

**切换快捷键**: `Ctrl/Cmd + B`

---

### 3.4 ChatBox 聊天区域

**文件**: `src/components/workspace/chats/chat-box.tsx`

```
┌─────────────────────────────────────────┬─────────────────────────┐
│                                         │                         │
│  ┌───────────────────────────────────┐  │  Artifacts Panel       │
│  │                                   │  │  (可调整宽度)          │
│  │         MessageList               │  │                        │
│  │                                   │  │  ┌─────────────────┐  │
│  │                                   │  │  │ Header          │  │
│  │                                   │  │  └─────────────────┘  │
│  │                                   │  │  ┌─────────────────┐  │
│  │                                   │  │  │                 │  │
│  ├───────────────────────────────────┤  │  │  FileList /     │  │
│  │           InputBox                │  │  │  FileDetail     │  │
│  └───────────────────────────────────┘  │  │                 │  │
│                                         │  └─────────────────┘  │
└─────────────────────────────────────────┴─────────────────────────┘
```

**ResizablePanel 配置**:
```tsx
<ResizablePanelGroup direction="horizontal">
  <ResizablePanel id="chat" defaultSize={100} minSize={30}>
    {children}  {/* MessageList + InputBox */}
  </ResizablePanel>

  <ResizableHandle withHandle id="separator" />

  <ResizablePanel id="artifacts" defaultSize={0} minSize={20}>
    {/* Artifacts content */}
  </ResizablePanel>
</ResizablePanelGroup>
```

**打开时比例**: `{ chat: 60, artifacts: 40 }`

---

### 3.5 MessageList 消息列表

**文件**: `src/components/workspace/messages/message-list.tsx`

**容器**:
```tsx
<Conversation className="flex size-full flex-col justify-center">
  <ConversationContent className="mx-auto w-full max-w-(--container-width-md) gap-8 pt-12">
    {/* messages */}
  </ConversationContent>
</Conversation>
```

**尺寸**:
- 最大宽度: `max-w-(--container-width-md)`
- 消息间距: `gap-8`
- 顶部padding: `pt-12`
- 底部spacer: `160px` (默认), `80px` (有followups时)

**消息结构**:
```tsx
{groupedMessages.map((group) => {
  if (group.type === "human" || group.type === "assistant") {
    return <MessageListItem key={group.id} message={group} />;
  }
  if (group.type === "assistant:clarification") {
    return <MarkdownContent key={group.id} content={group.content} />;
  }
  if (group.type === "assistant:subagent") {
    return (
      <MessageGroup key={group.id}>
        <SubtaskCard />
      </MessageGroup>
    );
  }
})}
```

---

### 3.6 MessageListItem 单条消息

**文件**: `src/components/workspace/messages/message-list-item.tsx`

```
┌─────────────────────────────────────────┐
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ [AI消息 - 左对齐]               │    │
│  │                                 │    │
│  │ Markdown 内容...                │    │
│  │                                 │    │
│  └─────────────────────────────────┘    │
│            ↗ hover显示工具栏            │
│                                         │
│                    ┌─────────────────────────────────┐
│                    │ [用户消息 - 右对齐]             │
│                    │                                 │
│                    │ 用户输入内容...                 │
│                    └─────────────────────────────────┘
│                                         │
└─────────────────────────────────────────┘
```

**AI消息 className**:
```tsx
<div className="w-full">
  <AIElementMessage type="user|assistant">
    <MessageContent className="w-full">
      <MarkdownContent />
    </MessageContent>
  </AIElementMessage>
</div>
```

**用户消息 className**:
```tsx
<div className="ml-auto flex flex-col gap-2">
  <AIElementMessage type="user">
    <MessageContent className="w-fit">
      {/* 内容 */}
    </MessageContent>
  </AIElementMessage>
</div>
```

**工具栏 (hover显示)**:
```tsx
<div className="absolute right-0 left-0 z-20 opacity-0 transition-opacity delay-200 duration-300
               group-hover:opacity-100
               -bottom-8 justify-end">
  <CopyButton />
</div>
```

---

### 3.7 InputBox 输入框

**文件**: `src/components/workspace/input-box.tsx`

```
┌────────────────────────────────────────────────────────────────────┐
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  💡 Flash  │ 💡 Thinking  │ 🎓 Pro  │ 🚀 Ultra              │   │ ← Mode菜单
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                                                             │   │
│  │  [输入框 - 多行文本]                                         │   │
│  │                                                             │   │
│  │                                                             │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  [+附件] [📎 Mode▾] [Reasoning▾]           [模型选择] [▶ 发送]    │
│   左侧工具                    右侧工具                              │
└────────────────────────────────────────────────────────────────────┘
```

**根容器**:
```tsx
<div className="relative flex flex-col gap-4">
  {/* Followups */}
  {/* PromptInput */}
</div>
```

**PromptInput className**:
```tsx
<PromptInput
  className="bg-background/85 rounded-2xl backdrop-blur-sm
             transition-all duration-300 ease-out"
>
  {/* ExtraHeader (Mode选择) */}
  {/* Attachments */}
  {/* Textarea */}
  {/* Footer */}
</PromptInput>
```

**Footer 布局**:
```tsx
<div className="flex">
  {/* 左侧工具 */}
  <PromptInputTools>
    <AddAttachmentsButton />
    <ModeMenu />       {/* Flash/Thinking/Pro/Ultra */}
    <ReasoningMenu />  {/* minimal/low/medium/high */}
  </PromptInputTools>

  {/* 右侧工具 */}
  <PromptInputTools>
    <ModelSelector />
    <PromptInputSubmit />
  </PromptInputTools>
</div>
```

**Mode 选项**:
| Mode | Icon | 描述 |
|------|------|------|
| flash | ZapIcon | 最快响应 |
| thinking | LightbulbIcon | 低推理投入 |
| pro | GraduationCapIcon | 中等推理投入 |
| ultra | RocketIcon | 高推理投入 (金色文字) |

**Reasoning Effort 选项**:
| Level | 描述 |
|-------|------|
| minimal | 检索 + 直接输出 |
| low | 简单逻辑校验 + 浅层推演 |
| medium | 多层逻辑分析 + 基础验证 |
| high | 全维度逻辑推演 + 多路径验证 |

**输入框样式**:
```tsx
<Textarea
  className="max-h-[240px] min-h-[56px] resize-none border-0 bg-transparent
             px-4 py-4 text-sm shadow-none focus-visible:ring-0"
  placeholder="How can I assist you today?"
/>
```

---

## 4. 组件库

### 4.1 Button

**变体 (variant)**:
- `default`: `bg-primary text-primary-foreground hover:bg-primary/90`
- `destructive`: `bg-destructive text-destructive-foreground hover:bg-destructive/90`
- `outline`: `border border-input bg-background hover:bg-accent hover:text-accent-foreground`
- `secondary`: `bg-secondary text-secondary-foreground hover:bg-secondary/80`
- `ghost`: `hover:bg-accent hover:text-accent-foreground`
- `link`: `text-primary underline-offset-4 hover:underline`

**尺寸 (size)**:
- `default`: `h-10 px-4 py-2`
- `sm`: `h-9 px-3`
- `lg`: `h-11 px-8`
- `icon`: `h-10 w-10`

**圆角**: `rounded-lg` (`--radius-lg`)

---

### 4.2 Card

```tsx
<div className="overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm" />
```

---

### 4.3 Dialog

**Overlay**: `fixed inset-0 z-50 bg-black/80`

**Content**:
```tsx
<DialogContent className="fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg
                          translate-x-[-50%] translate-y-[-50%] gap-4
                          border bg-background p-6 shadow-lg sm:rounded-lg">
  {/* Header, Content, Footer */}
</DialogContent>
```

---

### 4.4 DropdownMenu

```tsx
<DropdownMenuContent
  className="z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1
             text-popover-foreground shadow-md"
  align="end"
  sideOffset={4}
/>
```

---

### 4.5 Sidebar (shadcn/ui)

**来自**: `@/components/ui/sidebar.tsx`

**CSS变量**:
```css
--sidebar-width: 16rem;
--sidebar-width-icon: 3rem;
--sidebar-width-mobile: 18rem;
```

**使用方式**:
```tsx
<Sidebar variant="sidebar" collapsible="icon">
  <SidebarHeader>...</SidebarHeader>
  <SidebarContent>...</SidebarContent>
  <SidebarFooter>...</SidebarFooter>
</Sidebar>
```

---

### 4.6 ResizablePanel

**来自**: `recharts` 的 `ResizablePanelGroup`

```tsx
<ResizablePanelGroup direction="horizontal|vertical">
  <ResizablePanel defaultSize={50} minSize={20}>
    {/* content */}
  </ResizablePanel>
  <ResizableHandle />
  <ResizablePanel defaultSize={50} minSize={20}>
    {/* content */}
  </ResizablePanel>
</ResizablePanelGroup>
```

---

### 4.7 Terminal

**来自**: `@/components/ui/terminal`

```tsx
<Terminal className="h-[360px] w-full">
  <TypingAnimation>$ command</TypingAnimation>
  <AnimatedSpan delay={800} className="text-zinc-400">
    output
  </AnimatedSpan>
</Terminal>
```

---

### 4.8 AuroraText

**来自**: `@/components/ui/aurora-text`

```tsx
<AuroraText colors={["#60A5FA", "#A5FA60", "#A560FA"]}>
  Text Here
</AuroraText>
```

**动画**: 8秒循环渐变

---

### 4.9 WordRotate

**来自**: `@/components/ui/word-rotate`

```tsx
<WordRotate
  words={["Word1", "Word2", "Word3"]}
  duration={2000}
/>
```

---

### 4.10 FlickeringGrid

**来自**: `@/components/ui/flickering-grid`

**参数**:
- `squareSize`: 4
- `gridGap`: 4
- `color`: "white"
- `maxOpacity`: 0.3
- `flickerChance`: 0.25

---

### 4.11 MagicBento

**来自**: `@/components/ui/magic-bento`

**卡片类型**:
```tsx
interface BentoCardProps {
  color: string;
  label: string;
  title: string;
  description?: string;
}
```

---

## 附录: 响应式断点

| Breakpoint | Value |
|------------|-------|
| sm | 640px |
| md | 768px |
| lg | 1024px |
| xl | 1280px |
| 2xl | 1536px |

**常用响应式类**:
- `md:grid-cols-2` - 中屏双列
- `lg:grid-cols-3` - 大屏三列
- `lg:flex-row` - 大屏改为水平布局

---

## 附录: 常用间距

| Class | Value |
|-------|-------|
| `gap-2` | 8px |
| `gap-4` | 16px |
| `gap-6` | 24px |
| `gap-8` | 32px |
| `gap-12` | 48px |
| `gap-16` | 64px |

**常用padding**:
| Class | Value |
|-------|-------|
| `p-4` | 16px |
| `px-4` | 16px horizontal |
| `py-4` | 16px vertical |
| `px-8` | 32px horizontal |

---

*文档版本: 1.0*
*最后更新: 2026-04-28*
