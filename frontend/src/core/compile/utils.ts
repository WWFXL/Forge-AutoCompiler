import type { Message } from "@langchain/langgraph-sdk";

function textContent(message: Message): string {
  return typeof message.content === "string"
    ? message.content
    : message.content
        .filter((block) => block.type === "text")
        .map((block) => ("text" in block ? block.text : ""))
        .join("\n");
}

function preparedSession(content: string): string | undefined {
  try {
    const data: unknown = JSON.parse(content);
    if (data && typeof data === "object" && "session_id" in data) {
      const id = data.session_id;
      if (
        typeof id === "string" &&
        /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(id)
      ) {
        return id;
      }
    }
  } catch {
    const match =
      /\bsession_id=([A-Za-z0-9][A-Za-z0-9_-]{0,127})(?=[,\s]|$)/.exec(content);
    return match?.[1];
  }
}

// 只消费目标 task 之前的 prepare 结果，避免历史卡片串到后续会话。
export function findCompileSessionForTask(
  messages: Message[],
  taskId: string,
): string | undefined {
  const calls = new Map<string, string>();
  let sessionId: string | undefined;
  let prepareCallId: string | undefined;
  for (const message of messages) {
    if (message.type === "ai") {
      if (
        message.tool_calls?.some(
          (call) => call.id === taskId && call.name === "task",
        )
      ) {
        return sessionId;
      }
      for (const call of message.tool_calls ?? []) {
        if (call.id) calls.set(call.id, call.name);
        if (call.name === "prepare_compile_session") {
          sessionId = undefined;
          prepareCallId = call.id;
        }
      }
    } else if (
      message.type === "tool" &&
      message.tool_call_id === prepareCallId &&
      calls.get(message.tool_call_id) === "prepare_compile_session"
    ) {
      sessionId = preparedSession(textContent(message));
    }
  }
}
