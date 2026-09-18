import assert from "node:assert/strict";
import test from "node:test";

import type { Message } from "@langchain/langgraph-sdk";

const { groupMessages } = await import(
  new URL("./utils.ts", import.meta.url).href
);

function aiMessage({
  id,
  content = "",
  toolCallId,
  toolName = "finalize_session",
}: {
  id: string;
  content?: string;
  toolCallId?: string;
  toolName?: string;
}): Message {
  return {
    id,
    type: "ai",
    content,
    tool_calls: toolCallId
      ? [{ id: toolCallId, name: toolName, args: {}, type: "tool_call" }]
      : [],
  } as Message;
}

function toolMessage({
  id,
  toolCallId,
  name = "finalize_session",
}: {
  id: string;
  toolCallId: string;
  name?: string;
}): Message {
  return {
    id,
    type: "tool",
    content: "{}",
    name,
    tool_call_id: toolCallId,
  } as Message;
}

function groupedIds(messages: Message[]) {
  return groupMessages(messages, (group) => ({
    type: group.type,
    ids: group.messages.map((message) => message.id),
  }));
}

void test("groups an in-order tool result with its processing message", () => {
  assert.deepEqual(
    groupedIds([
      aiMessage({ id: "call", toolCallId: "tool-1" }),
      toolMessage({ id: "result", toolCallId: "tool-1" }),
      aiMessage({ id: "final", content: "完成" }),
    ]),
    [
      { type: "assistant:processing", ids: ["call", "result"] },
      { type: "assistant", ids: ["final"] },
    ],
  );
});

void test("backfills a late tool result by tool_call_id", () => {
  assert.deepEqual(
    groupedIds([
      aiMessage({ id: "call", toolCallId: "tool-1" }),
      aiMessage({ id: "final", content: "完成" }),
      toolMessage({ id: "result", toolCallId: "tool-1" }),
    ]),
    [
      { type: "assistant:processing", ids: ["call", "result"] },
      { type: "assistant", ids: ["final"] },
    ],
  );
});

void test("backfills a late subagent result into the matching subagent group", () => {
  assert.deepEqual(
    groupedIds([
      aiMessage({ id: "task-call", toolCallId: "task-1", toolName: "task" }),
      aiMessage({ id: "final", content: "子任务完成" }),
      toolMessage({ id: "task-result", toolCallId: "task-1", name: "task" }),
    ]),
    [
      {
        type: "assistant:subagent",
        ids: ["task-call", "task-result"],
      },
      { type: "assistant", ids: ["final"] },
    ],
  );
});

void test("ignores an unmatched tool result without logging a render error", () => {
  const originalError = console.error;
  const errors: unknown[][] = [];
  console.error = (...args: unknown[]) => errors.push(args);
  try {
    assert.deepEqual(
      groupedIds([
        aiMessage({ id: "final", content: "完成" }),
        toolMessage({ id: "orphan", toolCallId: "missing" }),
      ]),
      [{ type: "assistant", ids: ["final"] }],
    );
    assert.deepEqual(errors, []);
  } finally {
    console.error = originalError;
  }
});
