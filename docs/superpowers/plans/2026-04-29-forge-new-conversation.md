# Forge New Conversation Interface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/workspace/chats/new` with a Forge identity — gold/orange aesthetic, 3 action cards, sleek console input, and AnimatePresence exit animation on card click.

**Architecture:** Minimal changes to existing components. Add Forge hero + action cards to `welcome.tsx`. Update input placeholder and border. Add CSS for card hover glow. No backend changes.

**Tech Stack:** Next.js, React, Tailwind CSS 4, Framer Motion (existing), Lucide React

---

## File Map

| File | Changes |
|------|---------|
| `frontend/src/core/i18n/locales/zh-CN.ts` | Update `welcome` keys, add `actionCards` section |
| `frontend/src/core/i18n/locales/en-US.ts` | Mirror zh-CN changes |
| `frontend/src/core/i18n/locales/types.ts` | Add `actionCards` type to `Translations` |
| `frontend/src/styles/globals.css` | Add `.forge-hero`, `.forge-card`, `.forge-card:hover`, `.forge-input` |
| `frontend/src/components/workspace/welcome.tsx` | Replace greeting with Forge hero + action cards + AnimatePresence |
| `frontend/src/components/workspace/input-box.tsx:477` | Update placeholder text |

---

## Task 1: Update i18n — Chinese translations

**File:** `frontend/src/core/i18n/locales/zh-CN.ts`

- [ ] **Step 1: Update `welcome` section**

Replace lines 61–68 with:
```ts
  welcome: {
    greeting: "Forge: Autopilot for C/C++ Builds",
    description:
      "基于 Docker 隔离的端到端自动化构建流水线。智能嗅探环境、自动解析构建系统并执行排错，彻底告别依赖地狱。",

    createYourOwnSkill: "创建你自己的 Agent Skill",
    createYourOwnSkillDescription:
      "创建你的 Agent Skill 来释放 Forge 的潜力。通过自定义技能，Forge\n可以帮助你自动化构建、运行测试和高效编译代码。",

    actionCards: {
      cmakeTitle: "编译标准 CMake 项目",
      cmakeSubtitle: "例如: fmt",
      grpcTitle: "解析复杂子模块项目",
      grpcSubtitle: "例如: gRPC",
      ccacheTitle: "清理宿主机 CCache 缓存",
      ccacheSubtitle: "清理缓存释放空间",
    },
  },
```

- [ ] **Step 2: Update `inputBox.placeholder`**

Replace line 81:
```ts
    placeholder: ">_ 输入 GitHub 仓库地址或编译指令... [Press Enter to Forge]",
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/core/i18n/locales/zh-CN.ts
git commit -m "feat(i18n): update welcome and inputBox for Forge aesthetic"
```

---

## Task 2: Update i18n — English translations

**File:** `frontend/src/core/i18n/locales/en-US.ts`

- [ ] **Step 1: Update `welcome` section**

Replace the `welcome` block with:
```ts
  welcome: {
    greeting: "Forge: Autopilot for C/C++ Builds",
    description:
      "End-to-end automated build pipeline via Docker isolation. Intelligently detects environment, parses build systems, and troubleshoots errors — no more dependency hell.",
    createYourOwnSkill: "Create your own Agent Skill",
    createYourOwnSkillDescription:
      "Create your Agent Skill to unlock Forge's full potential. Custom skills help you automate builds, run tests, and compile code efficiently.",
    actionCards: {
      cmakeTitle: "Compile Standard CMake Project",
      cmakeSubtitle: "e.g. fmt",
      grpcTitle: "Parse Complex Submodule Project",
      grpcSubtitle: "e.g. gRPC",
      ccacheTitle: "Clean Host CCache",
      ccacheSubtitle: "Free up disk space",
    },
  },
```

- [ ] **Step 2: Update `inputBox.placeholder`**

```ts
    placeholder: ">_ Enter GitHub repo or build command... [Press Enter to Forge]",
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/core/i18n/locales/en-US.ts
git commit -m "feat(i18n): update welcome and inputBox for Forge aesthetic"
```

---

## Task 3: Update i18n — Translation types

**File:** `frontend/src/core/i18n/locales/types.ts`

- [ ] **Step 1: Add `actionCards` to `WelcomeScope`**

Find the `WelcomeScope` interface and add:
```ts
    actionCards: {
      cmakeTitle: string;
      cmakeSubtitle: string;
      grpcTitle: string;
      grpcSubtitle: string;
      ccacheTitle: string;
      ccacheSubtitle: string;
    };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/core/i18n/locales/types.ts
git commit -m "feat(i18n): add actionCards type for Forge welcome"
```

---

## Task 4: Add Forge CSS styles

**File:** `frontend/src/styles/globals.css`

- [ ] **Step 1: Add Forge card and hero styles**

Add before the closing `}` of the file or in the appropriate section:

```css
/* Forge Hero Section */
.forge-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.forge-hero-icon {
  font-size: 2.5rem;
  filter: drop-shadow(0 0 8px rgba(255, 107, 53, 0.4));
  animation: forge-spark 2s ease-in-out infinite;
}

@keyframes forge-spark {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(255, 107, 53, 0.3)); }
  50% { filter: drop-shadow(0 0 12px rgba(255, 107, 53, 0.6)); }
}

.forge-hero-title {
  font-size: 1.75rem;
  font-weight: 800;
  background: linear-gradient(135deg, #FFB800, #FF8C00);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0;
}

.forge-hero-subtitle {
  color: #6B7280;
  font-size: 0.875rem;
  max-width: 400px;
  text-align: center;
  line-height: 1.6;
  margin: 0;
}

/* Forge Action Cards */
.forge-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
  width: 100%;
  max-width: 500px;
  margin-bottom: 1rem;
}

.forge-card {
  background: #0a0a0a;
  border: 1px solid rgba(255, 107, 53, 0.3);
  border-radius: 0.5rem;
  padding: 1rem;
  cursor: pointer;
  transition: transform 0.2s ease-out, box-shadow 0.2s ease-out, border-color 0.2s ease-out;
  text-align: center;
}

.forge-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 107, 53, 0.6);
  box-shadow: 0 8px 32px rgba(255, 107, 53, 0.15), inset 0 0 0 1px rgba(255, 107, 53, 0.5);
}

.forge-card-icon {
  font-size: 1.5rem;
  margin-bottom: 0.25rem;
}

.forge-card-title {
  color: #E5E5E5;
  font-size: 0.75rem;
  font-weight: 600;
  margin: 0.25rem 0;
}

.forge-card-subtitle {
  color: #6B7280;
  font-size: 0.65rem;
  margin-top: 0.25rem;
  font-family: monospace;
}

/* Forge Input */
.forge-input {
  background: #000 !important;
  border: 2px solid #FFB800 !important;
  border-radius: 0.5rem;
  font-family: monospace !important;
}

.forge-input::placeholder {
  color: #6B7280;
  font-family: monospace;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/styles/globals.css
git commit -m "feat(css): add Forge hero and action card styles"
```

---

## Task 5: Update Welcome component

**File:** `frontend/src/components/workspace/welcome.tsx`

- [ ] **Step 1: Replace the component**

Replace the entire file content with:

```tsx
"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

let waved = false;

export function Welcome({
  className,
  mode,
  onCardClick,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
  onCardClick?: (text: string) => void;
}) {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const isUltra = useMemo(() => mode === "ultra", [mode]);
  const [dismissed, setDismissed] = useState(false);
  const colors = useMemo(() => {
    if (isUltra) {
      return ["#efefbb", "#e9c665", "#e3a812"];
    }
    return ["var(--color-foreground)"];
  }, [isUltra]);

  useEffect(() => {
    waved = true;
  }, []);

  const handleCardClick = (text: string) => {
    setDismissed(true);
    onCardClick?.(text);
  };

  const cardData = [
    {
      icon: "📦",
      title: t.welcome.actionCards.cmakeTitle,
      subtitle: t.welcome.actionCards.cmakeSubtitle,
      text: "克隆并编译标准现代 CMake 项目：https://github.com/fmtlib/fmt",
    },
    {
      icon: "🔗",
      title: t.welcome.actionCards.grpcTitle,
      subtitle: t.welcome.actionCards.grpcSubtitle,
      text: "克隆并深度解析编译 gRPC 项目：https://github.com/grpc/grpc，请注意处理子模块。",
    },
    {
      icon: "🧹",
      title: t.welcome.actionCards.ccacheTitle,
      subtitle: t.welcome.actionCards.ccacheSubtitle,
      text: "执行系统维护：清理宿主机挂载的 CCache 缓存。",
    },
  ];

  if (searchParams.get("mode") === "skill") {
    return (
      <div
        className={cn(
          "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
          className,
        )}
      >
        <div className="text-2xl font-bold">
          <div className="flex items-center gap-2">
            <div className={cn("inline-block", !waved ? "animate-wave" : "")}>
              ✨
            </div>
            <AuroraText colors={colors}>{t.welcome.createYourOwnSkill}</AuroraText>
          </div>
        </div>
        <div className="text-muted-foreground text-sm">
          <pre className="font-sans whitespace-pre">
            {t.welcome.createYourOwnSkillDescription}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
        className,
      )}
    >
      <AnimatePresence mode="wait">
        {!dismissed && (
          <motion.div
            key="forge-hero"
            initial={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="flex w-full flex-col items-center"
          >
            {/* Hero Section */}
            <div className="forge-hero">
              <div className="forge-hero-icon">🔨</div>
              <h1 className="forge-hero-title">
                <AuroraText colors={["#FFB800", "#FF8C00"]}>
                  {t.welcome.greeting}
                </AuroraText>
              </h1>
              <p className="forge-hero-subtitle">{t.welcome.description}</p>
            </div>

            {/* Action Cards */}
            <div className="forge-cards">
              {cardData.map((card) => (
                <div
                  key={card.text}
                  className="forge-card"
                  onClick={() => handleCardClick(card.text)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      handleCardClick(card.text);
                    }
                  }}
                >
                  <div className="forge-card-icon">{card.icon}</div>
                  <div className="forge-card-title">{card.title}</div>
                  <div className="forge-card-subtitle">{card.subtitle}</div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/welcome.tsx
git commit -m "feat(welcome): add Forge hero and action cards"
```

---

## Task 6: Expose input control from InputBox

**File:** `frontend/src/components/workspace/input-box.tsx`

- [ ] **Step 1: Add `inputRef` prop to InputBox**

Find the `InputBoxProps` interface (around line 116) and add:

```ts
inputRef?: React.MutableRefObject<{
  setInput: (text: string) => void;
  submit: () => void;
} | null>;
```

Then after `usePromptInputController()` call (line 137), add:

```ts
// Expose input control to parent
useEffect(() => {
  if (inputRef) {
    inputRef.current = {
      setInput: (text: string) => textInput.setInput(text),
      submit: () => requestFormSubmit(),
    };
  }
}, [inputRef, textInput, requestFormSubmit]);
```

- [ ] **Step 2: Update PromptInputTextarea with forge-input class**

Line 475–477, update:
```tsx
className={cn("size-full text-gray-100 placeholder:text-gray-500 forge-input")}
placeholder={t.inputBox.placeholder}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/input-box.tsx
git commit -m "feat(input): expose input control via inputRef and apply forge styling"
```

---

## Task 7: Wire Welcome card click to InputBox submit

**File:** `frontend/src/app/workspace/chats/[thread_id]/page.tsx`

- [ ] **Step 1: Add `inputControlRef` state and pass to Welcome + InputBox**

Add at the top of `ChatPage`:
```ts
const inputControlRef = useRef<{
  setInput: (text: string) => void;
  submit: () => void;
} | null>(null);
```

- [ ] **Step 2: Add `onCardClick` handler**

After `handleStop` definition, add:
```ts
const handleCardClick = useCallback(
  (text: string) => {
    inputControlRef.current?.setInput(text);
    // Small delay to let input populate before submit
    setTimeout(() => {
      inputControlRef.current?.submit();
    }, 50);
  },
  [],
);
```

- [ ] **Step 3: Pass props to Welcome and InputBox**

Update Welcome rendering (line 156):
```tsx
isNewThread && <Welcome mode={settings.context.mode} onCardClick={handleCardClick} />
```

Update InputBox rendering (line 142):
```tsx
<InputBox
  inputRef={inputControlRef}
  ...
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspace/chats/[thread_id]/page.tsx
git commit -m "feat(chat): wire action card click to input fill and submit"
```

---

## Task 8: Verify end-to-end

- [ ] **Step 1: Start dev server**

```bash
cd frontend && pnpm dev
```

- [ ] **Step 2: Open `/workspace/chats/new`**

Verify:
- [ ] Hero section shows 🔨 icon + gold gradient title
- [ ] 3 action cards visible with hover glow
- [ ] Input box has gold border and monospace placeholder
- [ ] Clicking a card fills the input
- [ ] After submit, welcome fades out smoothly
