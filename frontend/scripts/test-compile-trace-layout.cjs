// 仅使用离线 HTTP fixture；不创建编译容器、不调用模型。
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.FORGE_PLAYWRIGHT_PATH || "playwright");

const base = process.env.FORGE_TEST_BASE_URL || "http://127.0.0.1:3015";
assert.ok(
  ["127.0.0.1", "localhost"].includes(new URL(base).hostname),
  "只允许本地测试服务",
);
const output =
  process.env.FORGE_TEST_OUTPUT ||
  path.join(require("node:os").tmpdir(), "forge-compile-trace-layout");
fs.mkdirSync(output, { recursive: true });
const threadId = "a1111111-1111-4111-8111-111111111111";
const ai = (id, name, args = {}, content = "", reasoning = "") => ({
  id: `ai-${id}`,
  type: "ai",
  content,
  additional_kwargs: { reasoning_content: reasoning },
  tool_calls: [{ id, name, args }],
});
const tool = (id, content) => ({
  id: `tool-${id}`,
  type: "tool",
  tool_call_id: id,
  content,
});
const messages = [
  { id: "human-1", type: "human", content: "编译 FMT 并验证结果" },
];
for (const [index, sessionId] of ["session-old", "session-new"].entries()) {
  const prepare = `prepare-${index}`;
  const task = `task-${index}`;
  messages.push(
    ai(
      prepare,
      "prepare_compile_session",
      {},
      `中文过程正文：准备 ${sessionId}`,
      `Raw reasoning for ${sessionId}`,
    ),
    tool(
      prepare,
      `Compile session prepared. session_id=${sessionId}, container_id=test`,
    ),
  );
  messages.push(
    ai(
      `clone-${index}`,
      "clone_repository",
      {},
      "",
      `Clone reasoning for ${sessionId}`,
    ),
    tool(`clone-${index}`, "Repository cloned at /workspace/repo"),
  );
  messages.push(
    ai(task, "task", {
      subagent_type: "compiler",
      description: `编译与独立验证 ${sessionId}`,
      prompt: "构建固定 commit 并提交产物",
    }),
    tool(
      task,
      'Task Succeeded. Result: {"build_status":"success","summary":"build complete"}',
    ),
  );
}
messages.push({
  id: "final",
  type: "ai",
  content:
    "## 编译完成\n\n静态库通过产物验证与独立重放。\n\n最终正文末尾，可完整查看。",
  tool_calls: [],
});
const values = {
  messages,
  title: "FMT 离线展示回归",
  artifacts: [],
  todos: Array.from({ length: 6 }, (_, index) => ({
    content: `步骤 ${index + 1}：验证与清理容器，并保留完整产物和构建日志`,
    status: "completed",
  })),
};
const state = {
  values,
  next: [],
  tasks: [],
  interrupts: [],
  checkpoint: { thread_id: threadId, checkpoint_id: "fixture" },
  metadata: {},
  created_at: "2026-09-18T00:00:00Z",
  parent_checkpoint: null,
};

function snapshot(sessionId) {
  return {
    session_id: sessionId,
    status: "completed",
    repo_url: "https://github.com/fmtlib/fmt",
    commit_sha: "e".repeat(40),
    selected_build_system: "cmake",
    executed_build_system: "cmake",
    commands: ["clone", "configure", "build", "tests", "artifact_stage"].map(
      (role, index) => ({
        command_id: `${sessionId}-command-${index}`,
        stage: "bash",
        role,
        command:
          index === 1
            ? `cmake -S . -B build -D${"LONG_OPTION".repeat(32)}=ON`
            : `echo ${role}; cmake --build build`,
        workdir: "/workspace/repo",
        exit_code: index === 4 ? 126 : 0,
        duration_seconds: 1.25,
        timed_out: false,
        termination: index === 4 ? "policy_rejected" : null,
        has_log: true,
      }),
    ),
    artifacts: [
      {
        path: `${sessionId}/artifacts/lib/libfmt.a`,
        display_path: "lib/libfmt.a",
        artifact_type: "static_library",
        size_bytes: 253264,
        sha256: "a".repeat(64),
      },
      {
        path: `${sessionId}/artifacts/lib/libfmt-c.a`,
        display_path: "lib/libfmt-c.a",
        artifact_type: "static_library",
        size_bytes: 5642,
        sha256: "b".repeat(64),
      },
      ...["format.h", "core.h", "LICENSE"].map((name, index) => ({
        path: `${sessionId}/artifacts/${name}`,
        display_path: name === "LICENSE" ? name : `include/fmt/${name}`,
        artifact_type: "support_file",
        size_bytes: 100 + index,
        sha256: String(index + 1).repeat(64),
      })),
    ],
    verification: {
      status: "passed",
      checks: [
        { name: "archive", passed: true, summary: "valid static archive" },
      ],
    },
    replay_attempts: [
      {
        attempt_id: `${sessionId}-replay-1`,
        status: "failed",
        failure_classification: "smoke_mismatch",
        cleanup_succeeded: true,
        checks: [
          { name: "smoke", passed: false, summary: "first attempt differs" },
        ],
        has_log: true,
      },
      {
        attempt_id: `${sessionId}-replay-2`,
        status: "passed",
        failure_classification: null,
        cleanup_succeeded: true,
        checks: [
          { name: "smoke", passed: true, summary: "matches original output" },
        ],
        has_log: true,
      },
    ],
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
    for (const viewport of [
      { width: 1280, height: 900 },
      { width: 390, height: 844 },
      { width: 1280, height: 500 },
    ]) {
      const page = await browser.newPage({ viewport, locale: "zh-CN" });
      await page
        .context()
        .addCookies([{ name: "locale", value: "zh-CN", url: base }]);
      const errors = [];
      const logs = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("console", (message) => {
        if (message.type() === "error") errors.push(message.text());
      });
      await page.route("**/api/**", async (route) => {
        const url = new URL(route.request().url());
        const pathname = url.pathname;
        if (pathname.endsWith("/runs/stream")) {
          await new Promise((resolve) => setTimeout(resolve, 600));
          const completed = {
            ...values,
            messages: [
              ...messages,
              {
                id: "offline-followup",
                type: "ai",
                content: "离线 fixture 已完成",
                tool_calls: [],
              },
            ],
          };
          return route.fulfill({
            contentType: "text/event-stream",
            body: `event: metadata\ndata: ${JSON.stringify({ run_id: "offline-run", thread_id: threadId })}\n\nevent: values\ndata: ${JSON.stringify(completed)}\n\nevent: end\ndata: null\n\n`,
          });
        }
        if (
          pathname.endsWith("/compile-sessions/session-old") ||
          pathname.endsWith("/compile-sessions/session-new")
        )
          return route.fulfill({ json: snapshot(pathname.split("/").at(-1)) });
        if (
          pathname.includes("/compile-sessions/") &&
          pathname.endsWith("/log")
        ) {
          logs.push(pathname);
          return route.fulfill({
            json: {
              output:
                "CTest: 22/22 passed\n<unsafe-log-text>\n" +
                "long-output ".repeat(500),
              truncated: true,
            },
          });
        }
        if (pathname === "/api/models")
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
        if (pathname.endsWith("/suggestions"))
          return route.fulfill({
            json: {
              suggestions: [
                "查看本次构建结果和完整日志",
                "解释独立重放与清理结果",
              ],
            },
          });
        if (pathname.includes("/api/langgraph/")) {
          if (pathname.endsWith("/history"))
            return route.fulfill({ json: [state] });
          if (pathname.endsWith("/state"))
            return route.fulfill({ json: state });
          if (pathname.endsWith("/search") || pathname.endsWith("/runs"))
            return route.fulfill({ json: [] });
          return route.fulfill({
            json: {
              thread_id: threadId,
              values,
              status: "idle",
              metadata: {},
              updated_at: state.created_at,
            },
          });
        }
        return route.fulfill({ json: {} });
      });
      await page.goto(`${base}/workspace/chats/${threadId}`);
      const traces = page.getByTestId("compile-trace");
      await traces.nth(1).waitFor();
      assert.equal(await traces.count(), 2);
      assert.ok((await traces.nth(0).innerText()).includes("session-old"));
      assert.ok((await traces.nth(1).innerText()).includes("session-new"));
      assert.ok((await traces.nth(1).innerText()).includes("smoke_mismatch"));
      assert.ok((await traces.nth(1).innerText()).includes("2. passed"));
      assert.ok((await traces.nth(1).innerText()).includes("策略拒绝"));
      const artifacts = traces.nth(1).getByTestId("compile-artifacts");
      assert.ok((await artifacts.innerText()).includes("编译产物: 2"));
      assert.ok((await artifacts.innerText()).includes("lib/libfmt.a"));
      assert.ok((await artifacts.innerText()).includes("a".repeat(64)));
      const support = artifacts.getByTestId("compile-support-files");
      assert.equal(await support.getAttribute("open"), null);
      await support.locator("summary").click();
      assert.ok((await support.innerText()).includes("include/fmt/format.h"));
      assert.ok((await support.innerText()).includes("SHA-256"));
      const subtaskGroups = page.getByTestId("subtask-group");
      assert.equal(await subtaskGroups.count(), 2);
      for (let index = 0; index < (await subtaskGroups.count()); index++) {
        const bounds = await subtaskGroups.nth(index).evaluate((group) => {
          const title = group.querySelector('[data-testid="subtask-count"]');
          const card = title?.nextElementSibling;
          const unexpected = title?.previousElementSibling;
          const titleBox = title?.getBoundingClientRect();
          const cardBox = card?.getBoundingClientRect();
          return {
            unexpectedBeforeTitle: Boolean(unexpected),
            titleBottom: titleBox?.bottom,
            cardTop: cardBox?.top,
          };
        });
        assert.equal(
          bounds.unexpectedBeforeTitle,
          false,
          JSON.stringify(bounds),
        );
        assert.ok(
          bounds.titleBottom !== undefined &&
            bounds.cardTop !== undefined &&
            bounds.titleBottom < bounds.cardTop,
          JSON.stringify(bounds),
        );
      }
      const moreSteps = page.getByRole("button", { name: /查看.*步骤/ });
      while ((await moreSteps.count()) > 0) {
        await moreSteps.first().click();
      }
      const narrations = page.getByTestId("processing-narration");
      assert.equal(await narrations.count(), 2);
      assert.ok(
        (await narrations.nth(0).innerText()).includes(
          "中文过程正文：准备 session-old",
        ),
      );
      assert.ok(
        (await narrations.nth(1).innerText()).includes(
          "中文过程正文：准备 session-new",
        ),
      );
      const rawReasoning = page.getByTestId("raw-model-reasoning");
      assert.equal(await rawReasoning.count(), 4);
      for (let index = 0; index < (await rawReasoning.count()); index++) {
        const details = rawReasoning.nth(index).locator("details");
        assert.equal(await details.getAttribute("open"), null);
      }
      await rawReasoning.nth(0).locator("summary").click();
      assert.ok(
        (await rawReasoning.nth(0).innerText()).includes(
          "Raw reasoning for session-old",
        ),
      );
      assert.equal(logs.length, 0, "日志只能展开后读取");
      const command = traces.nth(1).locator("ol").first().locator("li").nth(1);
      await command.locator("summary").first().click();
      await command.getByText("输出日志", { exact: true }).click();
      await command.getByText("仅显示最后 16 KiB", { exact: false }).waitFor();
      assert.equal(logs.length, 1);
      assert.ok(logs[0].includes("session-new"));
      assert.equal(
        await page.locator("unsafe-log-text").count(),
        0,
        "日志不得被当作 HTML",
      );
      const todos = page.getByRole("button", { name: "To-dos" });
      for (let index = 0; index < 3; index++) {
        await todos.click();
        const bounds = await page.evaluate(() => {
          const message = document
            .querySelector('[data-testid="chat-messages"]')
            .getBoundingClientRect();
          const composer = document
            .querySelector('[data-testid="chat-composer"]')
            .getBoundingClientRect();
          return {
            messageBottom: message.bottom,
            composerTop: composer.top,
            messageHeight: message.height,
            overflow: document.documentElement.scrollWidth > innerWidth,
          };
        });
        assert.ok(
          bounds.messageBottom <= bounds.composerTop + 1,
          JSON.stringify(bounds),
        );
        assert.ok(bounds.messageHeight > 80, JSON.stringify(bounds));
        assert.equal(bounds.overflow, false);
      }
      await page.locator("textarea").fill("长输入不会覆盖消息。".repeat(60));
      await page
        .getByText("最终正文末尾，可完整查看。", { exact: false })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: path.join(
          output,
          `trace-${viewport.width}x${viewport.height}.png`,
        ),
      });
      await page.reload();
      await traces.nth(1).waitFor();
      assert.ok((await traces.nth(0).innerText()).includes("session-old"));
      assert.ok((await traces.nth(1).innerText()).includes("smoke_mismatch"));
      assert.deepEqual(errors, [], "不得新增浏览器错误");
      await page
        .locator("textarea")
        .fill("只提交到离线 fixture，检查 followups 布局");
      await page.locator("textarea").press("Enter");
      await page
        .getByRole("button", {
          name: "查看本次构建结果和完整日志",
          exact: true,
        })
        .waitFor();
      const followupBounds = await page.evaluate(() => {
        const message = document
          .querySelector('[data-testid="chat-messages"]')
          .getBoundingClientRect();
        const composer = document
          .querySelector('[data-testid="chat-composer"]')
          .getBoundingClientRect();
        return {
          bottom: message.bottom,
          top: composer.top,
          overflow: document.documentElement.scrollWidth > innerWidth,
        };
      });
      assert.ok(followupBounds.bottom <= followupBounds.top + 1);
      assert.equal(followupBounds.overflow, false);
      assert.deepEqual(errors, [], "离线任务结束不得新增浏览器错误");
      await page.screenshot({
        path: path.join(
          output,
          `followups-${viewport.width}x${viewport.height}.png`,
        ),
      });
      console.log(
        JSON.stringify({
          viewport,
          historyRefresh: true,
          noOverlap: true,
          lazyLog: true,
          passed: true,
        }),
      );
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
