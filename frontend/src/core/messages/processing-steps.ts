import type { AIMessage, Message, ToolMessage } from "@langchain/langgraph-sdk";

interface GenericProcessingStep<T extends string> {
  id: string | undefined;
  messageId: string | undefined;
  type: T;
}

export interface NarrationProcessingStep extends GenericProcessingStep<"narration"> {
  content: string;
}

export interface ReasoningProcessingStep extends GenericProcessingStep<"reasoning"> {
  reasoning: string;
}

export interface ToolCallProcessingStep extends GenericProcessingStep<"toolCall"> {
  name: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
}

export type ProcessingStep =
  | NarrationProcessingStep
  | ReasoningProcessingStep
  | ToolCallProcessingStep;

const THINK_TAG_RE = /<think>\s*([\s\S]*?)\s*<\/think>/g;

function splitInlineReasoning(content: string) {
  const reasoningParts: string[] = [];
  const cleaned = content
    .replace(THINK_TAG_RE, (_, reasoning: string) => {
      const normalized = reasoning.trim();
      if (normalized) reasoningParts.push(normalized);
      return "";
    })
    .trim();
  return {
    content: cleaned,
    reasoning: reasoningParts.length > 0 ? reasoningParts.join("\n\n") : null,
  };
}

function extractAIContent(message: AIMessage): string {
  if (typeof message.content === "string") {
    return splitInlineReasoning(message.content).content;
  }
  return message.content
    .map((part) => {
      if (part.type === "text") return part.text;
      const url =
        typeof part.image_url === "string"
          ? part.image_url
          : part.image_url.url;
      return `![image](${url})`;
    })
    .join("\n")
    .trim();
}

function extractReasoning(message: AIMessage): string | null {
  const configured = message.additional_kwargs?.reasoning_content;
  if (typeof configured === "string") return configured;
  if (Array.isArray(message.content)) {
    const first = message.content[0] as
      | ({ thinking?: unknown } & Record<string, unknown>)
      | undefined;
    if (typeof first?.thinking === "string") return first.thinking;
  }
  return typeof message.content === "string"
    ? splitInlineReasoning(message.content).reasoning
    : null;
}

function extractToolContent(message: ToolMessage): string {
  if (typeof message.content === "string") return message.content.trim();
  return message.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("\n")
    .trim();
}

function findToolResult(toolCallId: string, messages: Message[]) {
  for (const message of messages) {
    if (message.type === "tool" && message.tool_call_id === toolCallId) {
      const content = extractToolContent(message);
      if (content) return content;
    }
  }
  return undefined;
}

export function convertToProcessingSteps(
  messages: Message[],
): ProcessingStep[] {
  const steps: ProcessingStep[] = [];
  for (const message of messages) {
    if (message.type !== "ai") continue;

    const toolCalls = message.tool_calls ?? [];
    const content = extractAIContent(message);
    if (content && toolCalls.length > 0) {
      steps.push({
        id: message.id ? `${message.id}-content` : undefined,
        messageId: message.id,
        type: "narration",
        content,
      });
    }

    const reasoning = extractReasoning(message)?.trim();
    if (reasoning) {
      steps.push({
        id: message.id ? `${message.id}-reasoning` : undefined,
        messageId: message.id,
        type: "reasoning",
        reasoning,
      });
    }

    for (const toolCall of toolCalls) {
      if (toolCall.name === "task") continue;
      const step: ToolCallProcessingStep = {
        id: toolCall.id,
        messageId: message.id,
        type: "toolCall",
        name: toolCall.name,
        args: toolCall.args,
      };
      if (toolCall.id) {
        const result = findToolResult(toolCall.id, messages);
        if (result) {
          try {
            step.result = JSON.parse(result) as Record<string, unknown>;
          } catch {
            step.result = result;
          }
        }
      }
      steps.push(step);
    }
  }
  return steps;
}
