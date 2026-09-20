// 离线浏览器 fixture；不运行模型、容器或正式实验。
const assert = require("node:assert/strict");
const { chromium } = require(process.env.FORGE_PLAYWRIGHT_PATH || "playwright");

const base = process.env.FORGE_TEST_BASE_URL || "http://127.0.0.1:3017";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(base).hostname));
const threadId = "a1111111-1111-4111-8111-111111111111";
const sessionId = "session-fmt";
const messages = [
  { id: "user", type: "human", content: "编译 fmt" },
  {
    id: "prepare",
    type: "ai",
    content: "准备编译会话",
    additional_kwargs: {
      reasoning_content: "Inspect the session directory before cloning.",
    },
    tool_calls: [
      {
        id: "call-prepare",
        name: "prepare_compile_session",
        args: { repo_url: "https://github.com/fmtlib/fmt" },
      },
    ],
  },
  {
    id: "result",
    type: "tool",
    tool_call_id: "call-prepare",
    content: `session_id=${sessionId}`,
    status: "success",
  },
  {
    id: "delegate",
    type: "ai",
    content: "",
    tool_calls: [
      {
        id: "call-task",
        name: "task",
        args: { subagent_type: "compiler", description: "构建与验证" },
      },
    ],
  },
  {
    id: "task-result",
    type: "tool",
    tool_call_id: "call-task",
    content: 'Task Succeeded. Result: {"summary":"编译通过"}',
  },
  {
    id: "final",
    type: "ai",
    content: "编译成功，已通过重放。",
    tool_calls: [],
  },
];
const values = {
  title: "编译 fmt CMake 项目",
  messages,
  artifacts: [],
  todos: [{ content: "构建", status: "completed" }],
};
const metadata = {
  thread_id: threadId,
  created_at: "2026-09-20T01:00:00Z",
  updated_at: "2026-09-20T02:00:00Z",
  values,
  status: "idle",
  interrupts: {},
  metadata: {},
};
const session = {
  session_id: sessionId,
  status: "completed",
  repo_url: "https://github.com/fmtlib/fmt",
  commit_sha: "a".repeat(40),
  selected_build_system: "cmake",
  executed_build_system: "cmake",
  parallel_jobs: 4,
  commands: [
    {
      command_id: "command-build",
      stage: "bash",
      role: "build",
      command: "cmake --build build",
      workdir: "/workspace/repo",
      exit_code: 0,
      duration_seconds: 1.2,
      timed_out: false,
      termination: null,
      has_log: true,
    },
  ],
  artifacts: [
    {
      path: "session-fmt/artifacts/lib/libfmt.a",
      display_path: "lib/libfmt.a",
      artifact_type: "static_library",
      size_bytes: 120,
      sha256: "b".repeat(64),
    },
  ],
  verification: {
    status: "passed",
    checks: [{ name: "archive", passed: true, summary: "格式正确" }],
  },
  replay_attempts: [
    {
      attempt_id: "replay-1",
      status: "passed",
      duration_seconds: 3,
      failure_classification: null,
      cleanup_succeeded: true,
      verification_exit_code: 0,
      checks: [{ name: "match", passed: true }],
      has_log: true,
      has_verification_log: true,
    },
  ],
};

async function downloadedText(page, format) {
  const button = page.getByRole("button", { name: "导出", exact: true });
  await button.click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByText(`导出为 ${format}`, { exact: true }).click(),
  ]);
  const stream = await download.createReadStream();
  let text = "";
  for await (const chunk of stream) text += chunk.toString();
  return text;
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
      acceptDownloads: true,
      locale: "zh-CN",
    });
    await page
      .context()
      .addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    let failEvidence = false;
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === `/api/threads/${threadId}/compile-sessions/${sessionId}`)
        return route.fulfill({
          status: failEvidence ? 503 : 200,
          json: session,
        });
      if (path.endsWith("/commands/command-build/log"))
        return route.fulfill({
          json: {
            output:
              '完整命令原文\n</script><img src=x onerror="globalThis.pwned=true">',
            truncated: true,
          },
        });
      if (path.endsWith("/replays/replay-1/log"))
        return route.fulfill({
          json: { output: "重放构建输出", truncated: false },
        });
      if (path.endsWith("/replays/replay-1/verification-log"))
        return route.fulfill({
          json: { output: "22/22 CTest passed", truncated: false },
        });
      if (path === `/api/langgraph/threads/${threadId}`)
        return route.fulfill({ json: metadata });
      if (path.endsWith("/history")) return route.fulfill({ json: [] });
      if (path === "/api/models")
        return route.fulfill({ json: { models: [] } });
      if (path.endsWith("/search")) return route.fulfill({ json: [metadata] });
      if (path === `/api/langgraph/threads/${threadId}/state`)
        return route.fulfill({
          status: 404,
          json: { detail: "no checkpoint" },
        });
      if (path.endsWith("/runs")) return route.fulfill({ json: [] });
      return route.fulfill({ json: {} });
    });
    await page.goto(`${base}/workspace/chats/${threadId}`);
    await page.getByText("编译成功，已通过重放。").waitFor();

    const markdown = await downloadedText(page, "Markdown");
    for (const expected of [
      "Created",
      "2026",
      "repo_url",
      "session_id=session-fmt",
      "工具 `prepare_compile_session`",
      "原始工具结果",
      "cmake --build build",
      "完整命令原文",
      "原日志已截断",
      "22/22 CTest passed",
      "lib/libfmt.a",
      "SHA-256",
      "Inspect the session directory before cloning.",
      "模型返回的原始推理",
      "准备编译会话",
      "编译成功，已通过重放。",
    ]) {
      assert.ok(markdown.includes(expected), `Markdown 缺失: ${expected}`);
    }
    assert.ok(!markdown.includes("Created Unknown"));
    assert.ok(markdown.includes("<details>"));

    const html = await downloadedText(page, "HTML");
    for (const expected of [
      "<!doctype html>",
      "编译 fmt CMake 项目",
      "准备编译会话",
      "原始模型推理",
      "prepare_compile_session",
      "完整命令原文",
      "lib/libfmt.a",
      "Session API 原始响应",
    ]) {
      assert.ok(html.includes(expected), `HTML 缺失: ${expected}`);
    }
    assert.ok(html.includes("&lt;/script&gt;&lt;img"));
    assert.ok(!html.includes("<img src=x"));
    const report = await browser.newPage();
    await report.setContent(html);
    const toolDetails = report.locator("details.tool-call").first();
    assert.equal(await toolDetails.getAttribute("open"), null);
    await toolDetails.locator("summary").click();
    assert.ok(
      (await toolDetails.innerText()).includes("session_id=session-fmt"),
    );
    const reasoningDetails = report.locator("details.raw-reasoning").first();
    assert.equal(await reasoningDetails.getAttribute("open"), null);
    await reasoningDetails.locator("summary").click();
    assert.ok(
      (await reasoningDetails.innerText()).includes(
        "Inspect the session directory before cloning.",
      ),
    );
    await report.getByRole("button", { name: "全部展开" }).click();
    assert.equal(
      await report.locator("details:not([open])").count(),
      0,
      "全部展开必须打开报告中的每个 details",
    );
    await report.close();

    const json = JSON.parse(await downloadedText(page, "JSON"));
    assert.equal(json.created_at, metadata.created_at);
    assert.deepEqual(json.messages, messages);
    assert.equal(json.compile_sessions[0].session.session_id, sessionId);
    assert.equal(
      json.compile_sessions[0].command_logs["command-build"].truncated,
      true,
    );
    assert.equal(
      json.compile_sessions[0].replay_verification_logs["replay-1"].output,
      "22/22 CTest passed",
    );

    const historyItem = page
      .getByRole("link", { name: values.title })
      .locator("..");
    await historyItem.hover();
    await historyItem.getByRole("button", { name: "更多" }).click();
    await page.getByRole("menuitem", { name: "导出", exact: true }).hover();
    const [historyDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("menuitem", { name: "导出为 HTML" }).click(),
    ]);
    const historyStream = await historyDownload.createReadStream();
    let historyText = "";
    for await (const chunk of historyStream) historyText += chunk.toString();
    assert.ok(historyText.includes("<!doctype html>"));
    assert.ok(historyText.includes("cmake --build build"));
    assert.ok(historyText.includes("编译成功，已通过重放。"));

    failEvidence = true;
    await page.getByRole("button", { name: "导出", exact: true }).click();
    await page.getByText("导出为 Markdown", { exact: true }).click();
    await page.getByText("导出失败，编译证据未能完整读取").waitFor();
    console.log(
      JSON.stringify({
        markdown: true,
        html: true,
        json: true,
        history: true,
        evidenceFailure: true,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
