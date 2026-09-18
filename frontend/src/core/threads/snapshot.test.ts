import assert from "node:assert/strict";
import test from "node:test";

import type { AgentThread } from "./types.ts";

const { selectThreadSnapshotValues } = await import(
  new URL("./snapshot.ts", import.meta.url).href
);

function thread(threadId: string, messageIds: string[]): AgentThread {
  return {
    thread_id: threadId,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    metadata: {},
    status: "idle",
    interrupts: {},
    values: {
      title: `Thread ${threadId}`,
      messages: messageIds.map((id) => ({ id, type: "human", content: id })),
      artifacts: [],
    },
  };
}

void test("为当前线程返回持久化 snapshot values", () => {
  const snapshot = thread("thread-a", ["message-1", "message-2"]);

  assert.equal(
    selectThreadSnapshotValues("thread-a", snapshot),
    snapshot.values,
  );
});

void test("线程切换时拒绝前一个线程的 snapshot", () => {
  const snapshot = thread("thread-a", ["message-a"]);

  assert.equal(selectThreadSnapshotValues("thread-b", snapshot), null);
});

void test("新会话和尚未加载的 snapshot 不提供初始状态", () => {
  assert.equal(selectThreadSnapshotValues(null, thread("thread-a", [])), null);
  assert.equal(selectThreadSnapshotValues("thread-a", undefined), null);
});

void test("保留 snapshot 的完整状态而不重建消息", () => {
  const snapshot = thread("thread-a", ["message-1"]);
  snapshot.values.todos = [{ content: "完成构建", status: "completed" }];

  const values = selectThreadSnapshotValues("thread-a", snapshot);

  assert.equal(values, snapshot.values);
  assert.deepEqual(values?.todos, [
    { content: "完成构建", status: "completed" },
  ]);
});
