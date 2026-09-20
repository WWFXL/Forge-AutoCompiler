import assert from "node:assert/strict";
import test from "node:test";

import type { Message } from "@langchain/langgraph-sdk";

import type { CompileSessionEvidence } from "./export-evidence";
import type { AgentThread } from "./types";

const { formatThreadAsHTML, formatThreadAsJSON, formatThreadAsMarkdown } =
  await import(new URL("./export.ts", import.meta.url).href);

const injection = '</script><img src=x onerror="globalThis.pwned=true">';
const messages = [
  { id: "user", type: "human", content: "编译 fmt" },
  {
    id: "assistant",
    type: "ai",
    content: "编译会话已准备好。",
    additional_kwargs: { reasoning_content: "Session prepared." },
    tool_calls: [
      {
        id: "call-prepare",
        name: "prepare_compile_session",
        args: { repo_url: `https://example.com/${injection}` },
        type: "tool_call",
      },
    ],
  },
  {
    id: "result",
    type: "tool",
    name: "prepare_compile_session",
    tool_call_id: "call-prepare",
    status: "success",
    content: `session_id=session-fmt\n${injection}`,
  },
  {
    id: "orphan",
    type: "tool",
    name: "unknown_tool",
    tool_call_id: "missing-call",
    content: "未匹配结果仍需保留",
  },
  { id: "final", type: "ai", content: "编译完成。", tool_calls: [] },
] as Message[];

const thread = {
  thread_id: "thread-fmt",
  created_at: "2026-09-20T01:00:00Z",
  updated_at: "2026-09-20T01:05:00Z",
  metadata: {},
  status: "idle",
  interrupts: {},
  values: { title: "编译 fmt", messages, artifacts: [], todos: [] },
} as AgentThread;

const evidence = [
  {
    session: {
      session_id: "session-fmt",
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
        {
          path: "session-fmt/artifacts/include/fmt/format.h",
          display_path: "include/fmt/format.h",
          artifact_type: "support_file",
          size_bytes: 240,
          sha256: "c".repeat(64),
        },
      ],
      verification: { status: "passed", checks: [] },
      replay_attempts: [
        {
          attempt_id: "replay-1",
          status: "passed",
          duration_seconds: 3,
          failure_classification: null,
          cleanup_succeeded: true,
          verification_exit_code: 0,
          checks: [],
          has_log: true,
          has_verification_log: true,
        },
      ],
    },
    command_logs: {
      "command-build": {
        output: `build passed\n${injection}`,
        truncated: true,
      },
    },
    replay_logs: {
      "replay-1": { output: "replay passed", truncated: false },
    },
    replay_verification_logs: {
      "replay-1": { output: "verification passed", truncated: false },
    },
  },
] as CompileSessionEvidence[];

void test("Markdown 配对工具结果并折叠长证据", () => {
  const markdown = formatThreadAsMarkdown(thread, messages, evidence);

  assert.match(markdown, /<summary>工具 `prepare_compile_session`.*success/);
  assert.match(markdown, /session_id=session-fmt/);
  assert.match(markdown, /未匹配工具结果/);
  assert.match(markdown, /<summary>build · exit 0/);
  assert.match(markdown, /Session API 原始响应/);
  assert.match(markdown, /原日志已截断/);
  assert.equal(
    markdown.indexOf("编译会话已准备好。") <
      markdown.indexOf("模型返回的原始推理"),
    true,
  );
});

void test("HTML 是自包含报告并转义全部不受信任文本", () => {
  assert.equal(typeof formatThreadAsHTML, "function");
  const html = formatThreadAsHTML(thread, messages, evidence);

  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<details[^>]*class="tool-call"/);
  assert.match(html, /编译会话已准备好。/);
  assert.match(html, /原始模型推理/);
  assert.match(html, /&lt;\/script&gt;&lt;img/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /https?:\/\/[^<]*\.(?:css|js)(?:["'])/i);
  assert.match(html, /data-action="expand"/);
  assert.match(html, /data-action="collapse"/);
});

void test("JSON 继续保留原始消息和证据对象", () => {
  const json = JSON.parse(formatThreadAsJSON(thread, messages, evidence));
  assert.deepEqual(json.messages, messages);
  assert.deepEqual(json.compile_sessions, evidence);
});
