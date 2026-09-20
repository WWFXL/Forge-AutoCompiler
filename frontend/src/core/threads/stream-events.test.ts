import assert from "node:assert/strict";
import test from "node:test";

const { createToolEndEventHandler } = await import(
  new URL("./stream-events.ts", import.meta.url).href
);

void test("没有工具结束监听器时不订阅 LangChain events", () => {
  assert.equal(createToolEndEventHandler(undefined), undefined);
});

void test("只把 on_tool_end 映射为工具结束事件", () => {
  const received: Array<{ name: string; data: unknown }> = [];
  const handler = createToolEndEventHandler((event) => received.push(event));

  handler?.({ event: "on_tool_start", name: "setup_agent", data: {} });
  handler?.({
    event: "on_tool_end",
    name: "setup_agent",
    data: { output: "ok" },
  });

  assert.deepEqual(received, [{ name: "setup_agent", data: { output: "ok" } }]);
});
