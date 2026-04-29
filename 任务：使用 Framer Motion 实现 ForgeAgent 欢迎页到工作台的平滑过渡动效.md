



# 任务：使用 Framer Motion 实现 ForgeAgent 欢迎页到工作台的平滑过渡动效

当前项目已经完成了静态欢迎页（Hero 区域和快捷卡片）的 UI 打磨。现在需要引入交互动效：当用户点击卡片或在输入框发送第一条消息后，欢迎区域需要平滑淡出，输入框自动吸底，并无缝切换到对话日志流视图。

请按照以下步骤重构对应的 Chat / Page 主组件：

## 1. 状态判断逻辑
请确保从 Vercel AI SDK (如 `useChat`) 中获取 `messages` 数组或 `isLoading` 状态。
定义一个衍生状态：`const hasStarted = messages.length > 0 || isLoading;`
这个状态将作为控制 UI 切换的唯一开关。

## 2. 改造 Hero 区域 (使用 AnimatePresence)
引入 `AnimatePresence` 和 `motion` (来自 `framer-motion`)。
将大标题、副标题和三个快捷卡片所在的容器包裹在 `AnimatePresence` 中。
实现逻辑：
```tsx
<AnimatePresence>
  {!hasStarted && (
    <motion.div
      key="hero-section"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -40, filter: "blur(4px)" }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="flex flex-col items-center..."
    >
      {/* 标题、副标题和 ActionCards 放这里 */}
    </motion.div>
  )}
</AnimatePresence>
```

*注意：`exit` 状态中加入一点负数的 `y` 和轻微的 `blur`，能极大地提升“控制台推门进入”的高级感。*

## 3. 实现输入框 (Input Box) 的平滑吸底

Framer Motion 的牛逼之处在于 `layout` 属性。请将包裹输入框的外层容器改为 `<motion.div layout>`。 当上面的 `hero-section` 被卸载时，由于 DOM 结构变化，带有 `layout` 的输入框会自动平滑过渡到页面的底部。

```
<motion.div 
  layout 
  transition={{ duration: 0.5, type: "spring", bounce: 0.1 }}
  className="w-full max-w-3xl mx-auto..."
>
  {/* 你现有的 PromptInput / 输入框组件 */}
</motion.div>
```

## 4. 卡片点击事件绑定

确保 Action Cards 组件接收 `append` 方法。当卡片被点击时，直接调用 `append({ role: 'user', content: '卡片对应的指令' })`。这会立刻改变 `hasStarted` 状态，触发上述所有流畅的动画。

请先检查当前的页面 DOM 结构（特别是 flex 布局和高度设定的部分 `h-screen` / `flex-1`），确保布局支持上述的动画流转，然后一次性进行修改。

