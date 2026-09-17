import type { Model } from "../models/types";
import type { LocalSettings } from "../settings/local";

export type InputMode = "flash" | "thinking" | "pro" | "ultra";

export function getResolvedMode(
  mode: InputMode | undefined,
  supportsThinking: boolean,
): InputMode {
  if (mode === "thinking" && !supportsThinking) return "flash";
  return mode ?? (supportsThinking ? "pro" : "flash");
}

export function buildRunContext(
  context: LocalSettings["context"],
  model:
    | Pick<Model, "supports_thinking" | "supports_reasoning_effort">
    | undefined,
  threadId: string,
  extraContext?: Record<string, unknown>,
) {
  const mode = getResolvedMode(context.mode, model?.supports_thinking ?? false);
  // 先移除历史上下文中的值，不能仅靠菜单隐藏不支持的参数。
  const rest = {
    ...extraContext,
    ...context,
  };
  delete rest.reasoning_effort;
  const effort =
    context.reasoning_effort ??
    (mode === "ultra"
      ? "high"
      : mode === "pro"
        ? "medium"
        : mode === "thinking"
          ? "low"
          : undefined);

  return {
    ...rest,
    mode,
    thinking_enabled: mode !== "flash" && !!model?.supports_thinking,
    is_plan_mode: mode === "pro" || mode === "ultra",
    subagent_enabled: mode === "ultra",
    ...(model?.supports_reasoning_effort && effort
      ? { reasoning_effort: effort }
      : {}),
    thread_id: threadId,
  };
}
