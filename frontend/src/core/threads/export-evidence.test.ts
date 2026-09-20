import assert from "node:assert/strict";
import test from "node:test";

const { loadCompileEvidence } = await import(
  new URL("./export-evidence.ts", import.meta.url).href
);

void test("按会话读取命令、重放与验证日志，保留截断标记", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  const root = "/api/threads/thread/compile-sessions/session";
  const responses: Record<string, unknown> = {
    [root]: {
      session_id: "session",
      commands: [{ command_id: "build", has_log: true }],
      replay_attempts: [
        { attempt_id: "replay", has_log: true, has_verification_log: true },
      ],
      artifacts: [],
    },
    [`${root}/commands/build/log`]: { output: "原样构建日志", truncated: true },
    [`${root}/replays/replay/log`]: { output: "replay", truncated: false },
    [`${root}/replays/replay/verification-log`]: {
      output: "22/22 passed",
      truncated: false,
    },
  };
  globalThis.fetch = (async (input: string) => {
    calls.push(input);
    return new Response(JSON.stringify(responses[input]), {
      status: input in responses ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  try {
    const [evidence] = await loadCompileEvidence("", "thread", ["session"]);
    assert.equal(evidence.session.session_id, "session");
    assert.deepEqual(evidence.command_logs.build, {
      output: "原样构建日志",
      truncated: true,
    });
    assert.equal(evidence.replay_logs.replay.output, "replay");
    assert.equal(
      evidence.replay_verification_logs.replay.output,
      "22/22 passed",
    );
    assert.equal(calls.length, 4);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

void test("证据缺失必须失败，不能导出伪完整文档", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response("not found", { status: 404 })) as typeof fetch;
  try {
    await assert.rejects(
      loadCompileEvidence("", "thread", ["missing"]),
      /编译证据请求失败.*HTTP 404/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
