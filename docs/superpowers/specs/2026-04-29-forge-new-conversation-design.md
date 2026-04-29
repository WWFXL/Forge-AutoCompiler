# Forge New Conversation Interface — Design Spec

**Date:** 2026-04-29
**Author:** Claude Code
**Status:** Approved

---

## Context

The new conversation page (`/workspace/chats/new`) currently shows a simple greeting ("你好，欢迎回来！") with a basic input box. This is underwhelming for a hard-core C/C++ build automation system. The goal is to give the page a "Forge" identity — a sleek dark console aesthetic with gold/orange accents that communicates: this is a powerful build automation tool, not a generic chat UI.

---

## Design Language

### Aesthetic Direction
Sleek dark console — smooth lift on hover, subtle orange/amber neon glow, terminal aesthetic. Inspired by IDE/editor dark themes and cyberpunk forge imagery.

### Color Palette
- **Primary accent:** `#FFB800` (Forge Gold)
- **Secondary accent:** `rgba(255, 107, 53, 0.5)` (orange neon glow on hover)
- **Card background:** `#0a0a0a` (pure console black)
- **Card border:** `rgba(255, 107, 53, 0.3)` default, `rgba(255, 107, 53, 0.5)` on hover
- **Text primary:** `#E5E5E5`
- **Text muted:** `#6B7280`
- **Code snippets:** monospace font

### Typography
- Title: bold, large, gold gradient (`#FFB800` → `#FF8C00`)
- Body: system sans-serif
- Code/project names: `font-family: monospace`

### Motion
- Transitions: `0.2s–0.3s ease-out` — precise and efficient, no bounce/spring
- Card hover: `translateY(-2px)` + box-shadow glow
- Welcome exit: `opacity: 0, y: -20` via AnimatePresence (Framer Motion), 0.3s

---

## Components

### 1. Hero Section (`welcome.tsx`)
- **Icon:** 🔨 pixel anvil — slightly larger, subtle orange "spark" shadow beneath
- **Title:** "Forge: Autopilot for C/C++ Builds" — gold gradient via `AuroraText` or CSS gradient
- **Subtitle:** "基于 Docker 隔离的端到端自动化构建流水线。智能嗅探环境、自动解析构建系统并执行排错，彻底告别依赖地狱。"

### 2. Action Cards (3 cards above input)
Grid layout, 3 columns, equal width.

| Card | Icon | Title | Subtitle |
|------|------|-------|----------|
| 📦 Compile CMake | 📦 | 编译标准 CMake 项目 | 例如: fmt |
| 🔗 Parse Submodules | 🔗 | 解析复杂子模块项目 | 例如: gRPC |
| 🧹 Clean CCache | 🧹 | 清理宿主机 CCache 缓存 | 清理缓存释放空间 |

**Card styling:**
- Background: `#0a0a0a`
- Border: `1px solid rgba(255, 107, 53, 0.3)`
- Border-radius: `0.5rem`
- Padding: `1rem`
- Text: title in `#E5E5E5` (semibold), subtitle in `#6B7280`
- Project code (fmt, gRPC): monospace font
- **Hover state:** `translateY(-2px)` + `box-shadow: 0 8px 32px rgba(255, 107, 53, 0.15), inset 0 0 0 1px rgba(255, 107, 53, 0.5)`

**Interaction:**
1. User clicks card → preset instruction fills `input-box`
2. System auto-triggers submit (equivalent to pressing Enter)
3. Welcome section exits with AnimatePresence fade+slide-up (opacity 0, y -20, 0.3s ease-out)
4. Message list takes over the full area

### 3. Input Box (`input-box.tsx`)
- **Background:** pure black (`#000000`)
- **Border:** `2px solid #FFB800` (gold)
- **Placeholder:** `>_ 输入 GitHub 仓库地址或编译指令... [Press Enter to Forge]`
- Monospace font for placeholder text

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│                    Hero Section                         │
│         🔨 "Forge: Autopilot for C/C++ Builds"          │
│   Subtitle text in muted gray                          │
├─────────────────────────────────────────────────────────┤
│   ┌───────────┐  ┌───────────┐  ┌───────────┐          │
│   │  📦 CMake │  │🔗 gRPC   │  │🧹 CCache │          │
│   │  (fmt)   │  │ Submodules│  │  Cleanup  │          │
│   └───────────┘  └───────────┘  └───────────┘          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐   │
│  │ >_ 输入 GitHub 仓库地址或编译指令...            │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

After card click → welcome collapses → full chat area takes over.

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/components/workspace/welcome.tsx` | Add hero section with new icon/title/subtitle, add action cards grid |
| `frontend/src/components/workspace/input-box.tsx` | Update placeholder text and border style for Forge aesthetic |
| `frontend/src/styles/globals.css` | Add `.forge-card:hover` glow styles, `.forge-input` styles |
| `frontend/src/core/i18n/` | Add new i18n keys for title, subtitle, card labels |

---

## Implementation Notes

- Use existing `AuroraText` component for gold gradient title
- Use existing `motion` (Framer Motion) for AnimatePresence exit animation
- Action card click handler: fill input + call submit handler — no backend changes
- CSS classes: `.forge-card`, `.forge-card:hover`, `.forge-input`
- No changes to backend agent logic — cards are purely frontend UX shortcuts
