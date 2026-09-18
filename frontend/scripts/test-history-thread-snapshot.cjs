// 仅使用离线 HTTP fixture；不创建编译容器、不调用模型。
const assert = require("node:assert/strict");
const { chromium } = require(process.env.FORGE_PLAYWRIGHT_PATH || "playwright");

const base = process.env.FORGE_TEST_BASE_URL || "http://127.0.0.1:3016";
assert.ok(
  ["127.0.0.1", "localhost"].includes(new URL(base).hostname),
  "只允许本地测试服务",
);

const snapshotThreadId = "a1111111-1111-4111-8111-111111111111";
const historyThreadId = "b2222222-2222-4222-8222-222222222222";

function messages(prefix) {
  return [
    {
      id: `${prefix}-human`,
      type: "human",
      content: `${prefix} 用户消息`,
    },
    {
      id: `${prefix}-ai`,
      type: "ai",
      content: `${prefix} 助手消息`,
      tool_calls: [],
    },
  ];
}

function values(prefix) {
  return {
    title: `${prefix} 会话`,
    messages: messages(prefix),
    artifacts: [],
  };
}

function thread(threadId, threadValues) {
  return {
    thread_id: threadId,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    metadata: {},
    status: "idle",
    interrupts: {},
    values: threadValues,
  };
}

function state(threadId, stateValues) {
  return {
    values: stateValues,
    next: [],
    tasks: [],
    interrupts: [],
    checkpoint: { thread_id: threadId, checkpoint_id: "fixture" },
    metadata: {},
    created_at: "2026-09-18T00:00:00Z",
    parent_checkpoint: null,
  };
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.FORGE_CHROME_PATH
      ? { executablePath: process.env.FORGE_CHROME_PATH }
      : {}),
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 900 },
      locale: "zh-CN",
    });
    const errors = [];
    const snapshotGets = [];
    let historyCalls = 0;
    let streamCalls = 0;

    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (pathname === "/api/models") {
        return route.fulfill({
          json: {
            models: [
              {
                id: "test",
                name: "test",
                model: "test",
                display_name: "Offline Test",
                supports_thinking: false,
              },
            ],
          },
        });
      }
      if (pathname.endsWith("/runs/stream")) {
        streamCalls += 1;
        return route.fulfill({ status: 500, json: { detail: "unexpected" } });
      }
      if (pathname.endsWith("/history")) {
        historyCalls += 1;
        if (pathname.includes(historyThreadId)) {
          return route.fulfill({
            json: [state(historyThreadId, values("history-wins"))],
          });
        }
        return route.fulfill({ json: [] });
      }
      if (pathname.endsWith("/search") || pathname.endsWith("/runs")) {
        return route.fulfill({ json: [] });
      }
      if (pathname.includes("/api/langgraph/threads/")) {
        const threadId = pathname.split("/").at(-1);
        snapshotGets.push(threadId);
        const snapshotValues =
          threadId === historyThreadId
            ? values("snapshot-must-not-win")
            : values("snapshot-fallback");
        return route.fulfill({ json: thread(threadId, snapshotValues) });
      }
      if (pathname.includes("/api/langgraph/")) {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({ json: {} });
    });

    await page.goto(`${base}/workspace/chats/${snapshotThreadId}`);
    await page
      .getByText("snapshot-fallback 助手消息", { exact: true })
      .waitFor();
    assert.equal(
      await page
        .getByText("snapshot-fallback 用户消息", { exact: true })
        .count(),
      1,
    );

    await page.goto(`${base}/workspace/chats/${historyThreadId}`);
    await page.getByText("history-wins 助手消息", { exact: true }).waitFor();
    assert.equal(
      await page
        .getByText("snapshot-must-not-win 助手消息", { exact: true })
        .count(),
      0,
    );

    assert.deepEqual(
      [...new Set(snapshotGets)].sort(),
      [historyThreadId, snapshotThreadId].sort(),
    );
    assert.ok(
      snapshotGets.filter((threadId) => threadId === snapshotThreadId).length >=
        1,
    );
    assert.ok(
      snapshotGets.filter((threadId) => threadId === historyThreadId).length >=
        1,
    );
    assert.ok(historyCalls >= 2, "两个线程都必须尝试读取官方 history");
    assert.equal(streamCalls, 0, "查看历史不得触发模型 run");
    assert.deepEqual(errors, [], "历史回退不得产生浏览器错误");
    console.log(
      JSON.stringify({
        directURL: true,
        emptyHistoryFallback: true,
        historyPrecedence: true,
        noModelRun: true,
        passed: true,
      }),
    );
    await page.close();
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
