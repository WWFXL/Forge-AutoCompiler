import type { AIMessage, Message, ToolMessage } from "@langchain/langgraph-sdk";

import type { CompileLog } from "../compile/types";

import type { CompileSessionEvidence } from "./export-evidence";
import type { AgentThread } from "./types";

type ToolCall = NonNullable<AIMessage["tool_calls"]>[number];

interface ToolAssociation {
  call: ToolCall;
  result: ToolMessage | undefined;
}

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

function extractContentFromMessage(message: Message): string {
  if (typeof message.content === "string") {
    return message.type === "ai"
      ? splitInlineReasoning(message.content).content
      : message.content.trim();
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

function extractReasoningContentFromMessage(message: AIMessage) {
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

function titleOfThread(thread: AgentThread) {
  return thread.values?.title ?? "Untitled";
}

function block(content: string, language = "text"): string {
  let length = 3;
  for (const [run] of content.matchAll(/`+/g)) {
    length = Math.max(length, run.length + 1);
  }
  const fence = "`".repeat(length);
  return `${fence}${language}\n${content}\n${fence}`;
}

function escapeHTML(value: unknown): string {
  const text =
    typeof value === "string"
      ? value
      : value == null
        ? ""
        : (JSON.stringify(value) ?? "");
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function stringify(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "null";
}

function toolStatus(message: ToolMessage | undefined): string {
  if (!message) return "pending";
  return message.status ?? "returned";
}

function associateTools(messages: Message[]): {
  byMessage: Map<AIMessage, ToolAssociation[]>;
  unmatched: ToolMessage[];
} {
  const results = new Map<string, ToolMessage>();
  for (const message of messages) {
    if (message.type === "tool" && message.tool_call_id) {
      results.set(message.tool_call_id, message);
    }
  }

  const consumed = new Set<ToolMessage>();
  const byMessage = new Map<AIMessage, ToolAssociation[]>();
  for (const message of messages) {
    if (message.type !== "ai") continue;
    const associations = (message.tool_calls ?? []).map((call) => {
      const result = call.id ? results.get(call.id) : undefined;
      if (result) consumed.add(result);
      return { call, result };
    });
    if (associations.length) byMessage.set(message, associations);
  }

  return {
    byMessage,
    unmatched: messages.filter(
      (message): message is ToolMessage =>
        message.type === "tool" && !consumed.has(message),
    ),
  };
}

function markdownDetails(
  summary: string,
  body: string[],
  options: { open?: boolean } = {},
): string[] {
  return [
    `<details${options.open ? " open" : ""}>`,
    `<summary>${escapeHTML(summary)}</summary>`,
    "",
    ...body,
    "",
    "</details>",
    "",
  ];
}

function markdownLog(label: string, log: CompileLog): string[] {
  return [
    `**${label}${log.truncated ? "（仅保留末尾 16 KiB，原日志已截断）" : ""}**`,
    "",
    block(log.output),
    "",
  ];
}

function formatCompileEvidenceMarkdown(
  evidence: CompileSessionEvidence,
): string[] {
  const { session, command_logs, replay_logs, replay_verification_logs } =
    evidence;
  const lines = [
    `## 编译会话 ${session.session_id}`,
    "",
    `- 状态：${session.status}`,
    `- 仓库：${session.repo_url ?? "未记录"}`,
    `- 提交：${session.commit_sha ?? "未记录"}`,
    `- 构建系统：${session.executed_build_system ?? session.selected_build_system ?? "未记录"}`,
    "",
    "### 编译命令",
    "",
  ];

  for (const command of session.commands) {
    const body = [
      `- ID：\`${command.command_id}\``,
      `- 目录：\`${command.workdir}\``,
      `- 终止原因：${command.termination ?? "无"}；耗时：${command.duration_seconds ?? "未记录"} 秒；超时：${command.timed_out}`,
      "",
      block(command.command, "bash"),
      "",
    ];
    const log = command_logs[command.command_id];
    if (log) body.push(...markdownLog("命令输出", log));
    lines.push(
      ...markdownDetails(
        `${command.role || command.stage} · exit ${command.exit_code ?? "unknown"} · ${command.command_id}`,
        body,
        { open: command.exit_code !== 0 || command.timed_out },
      ),
    );
  }

  const compiled = session.artifacts.filter(
    (artifact) => artifact.artifact_type !== "support_file",
  );
  const support = session.artifacts.filter(
    (artifact) => artifact.artifact_type === "support_file",
  );
  lines.push("### 编译产物", "");
  for (const artifact of compiled) {
    lines.push(
      `- \`${artifact.display_path}\`：${artifact.artifact_type}；${artifact.size_bytes ?? "未记录"} B；SHA-256 \`${artifact.sha256 ?? "未记录"}\``,
    );
  }
  if (!compiled.length) lines.push("- 无", "");
  if (support.length) {
    lines.push(
      "",
      ...markdownDetails(
        `辅助文件（${support.length}）`,
        support.map(
          (artifact) =>
            `- \`${artifact.display_path}\`：${artifact.size_bytes ?? "未记录"} B；SHA-256 \`${artifact.sha256 ?? "未记录"}\``,
        ),
      ),
    );
  }

  lines.push(
    "### 验证与重放",
    "",
    ...markdownDetails(
      `候选验证 · ${session.verification?.status ?? "未记录"}`,
      [block(stringify(session.verification), "json")],
      { open: session.verification?.status === "failed" },
    ),
  );
  for (const attempt of session.replay_attempts) {
    const body = [block(stringify(attempt), "json"), ""];
    const replayLog = replay_logs[attempt.attempt_id];
    if (replayLog) body.push(...markdownLog("重放日志", replayLog));
    const verificationLog = replay_verification_logs[attempt.attempt_id];
    if (verificationLog)
      body.push(...markdownLog("重放验证日志", verificationLog));
    lines.push(
      ...markdownDetails(
        `重放 ${attempt.attempt_id} · ${attempt.status}`,
        body,
        { open: attempt.status !== "passed" },
      ),
    );
  }
  lines.push(
    ...markdownDetails("Session API 原始响应", [
      block(stringify(session), "json"),
    ]),
  );
  return lines;
}

export function formatThreadAsMarkdown(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
): string {
  const createdAt = thread.created_at
    ? new Date(thread.created_at).toLocaleString()
    : "Unknown";
  const lines: string[] = [
    `# ${titleOfThread(thread)}`,
    "",
    `*Exported on ${new Date().toLocaleString()} · Created ${createdAt}*`,
    "",
    `Thread ID: \`${thread.thread_id}\``,
    "",
    "---",
    "",
  ];
  const tools = associateTools(messages);

  for (const message of messages) {
    if (message.type === "human") {
      const content = extractContentFromMessage(message);
      if (content) lines.push("## 用户", "", content, "", "---", "");
      continue;
    }
    if (message.type !== "ai") continue;

    const content = extractContentFromMessage(message);
    const reasoning = extractReasoningContentFromMessage(message)?.trim();
    const associations = tools.byMessage.get(message) ?? [];
    if (!content && !reasoning && !associations.length) continue;

    lines.push("## 助手", "");
    if (content) lines.push(content, "");
    if (reasoning) {
      lines.push(...markdownDetails("模型返回的原始推理", [block(reasoning)]));
    }
    for (const { call, result } of associations) {
      const body = ["**参数**", "", block(stringify(call.args), "json")];
      if (result) {
        body.push("", "**原始工具结果**", "", block(stringify(result), "json"));
      } else {
        body.push("", "尚未记录工具结果。");
      }
      lines.push(
        ...markdownDetails(
          `工具 \`${call.name}\` · ${toolStatus(result)} · ${call.id ?? "无 ID"}`,
          body,
        ),
      );
    }
    lines.push("---", "");
  }

  for (const message of tools.unmatched) {
    lines.push(
      ...markdownDetails(
        `未匹配工具结果 · ${message.name ?? "未知工具"} · ${message.tool_call_id ?? "无 ID"}`,
        [block(stringify(message), "json")],
      ),
    );
  }
  if (thread.values?.todos?.length) {
    lines.push(
      ...markdownDetails("导出时任务状态", [
        block(stringify(thread.values.todos), "json"),
      ]),
    );
  }
  if (compileSessions.length) {
    lines.push("# 编译证据", "");
    for (const evidence of compileSessions) {
      lines.push(...formatCompileEvidenceMarkdown(evidence));
    }
  }
  return lines.join("\n").trimEnd() + "\n";
}

function htmlPre(value: unknown, className = "raw"): string {
  return `<pre class="${className}"><code>${escapeHTML(
    typeof value === "string" ? value : stringify(value),
  )}</code></pre>`;
}

function htmlDetails(
  summary: string,
  body: string,
  className: string,
  open = false,
): string {
  return `<details class="${className}"${open ? " open" : ""}><summary>${escapeHTML(summary)}</summary><div class="details-body">${body}</div></details>`;
}

function htmlLog(label: string, log: CompileLog): string {
  return `<h4>${escapeHTML(label)}${log.truncated ? '<span class="warning">仅保留末尾 16 KiB，原日志已截断</span>' : ""}</h4>${htmlPre(log.output)}`;
}

function formatCompileEvidenceHTML(evidence: CompileSessionEvidence): string {
  const { session, command_logs, replay_logs, replay_verification_logs } =
    evidence;
  const commands = session.commands
    .map((command) => {
      const log = command_logs[command.command_id];
      const body = `<dl><dt>ID</dt><dd>${escapeHTML(command.command_id)}</dd><dt>目录</dt><dd>${escapeHTML(command.workdir)}</dd><dt>终止原因</dt><dd>${escapeHTML(command.termination ?? "无")}</dd><dt>耗时</dt><dd>${escapeHTML(command.duration_seconds ?? "未记录")} 秒</dd></dl>${htmlPre(command.command, "command")}${log ? htmlLog("命令输出", log) : ""}`;
      return htmlDetails(
        `${command.role || command.stage} · exit ${command.exit_code ?? "unknown"} · ${command.command_id}`,
        body,
        "command-record",
        command.exit_code !== 0 || command.timed_out,
      );
    })
    .join("");
  const artifacts = session.artifacts
    .map(
      (artifact) =>
        `<tr><td>${escapeHTML(artifact.display_path)}</td><td>${escapeHTML(artifact.artifact_type)}</td><td>${escapeHTML(artifact.size_bytes ?? "未记录")}</td><td><code>${escapeHTML(artifact.sha256 ?? "未记录")}</code></td></tr>`,
    )
    .join("");
  const replays = session.replay_attempts
    .map((attempt) => {
      const replayLog = replay_logs[attempt.attempt_id];
      const verificationLog = replay_verification_logs[attempt.attempt_id];
      const body = `${htmlPre(attempt)}${replayLog ? htmlLog("重放日志", replayLog) : ""}${verificationLog ? htmlLog("重放验证日志", verificationLog) : ""}`;
      return htmlDetails(
        `重放 ${attempt.attempt_id} · ${attempt.status}`,
        body,
        "replay-record",
        attempt.status !== "passed",
      );
    })
    .join("");
  return `<section class="compile-session"><h2>编译会话 ${escapeHTML(session.session_id)}</h2><dl><dt>状态</dt><dd>${escapeHTML(session.status)}</dd><dt>仓库</dt><dd>${escapeHTML(session.repo_url ?? "未记录")}</dd><dt>提交</dt><dd><code>${escapeHTML(session.commit_sha ?? "未记录")}</code></dd><dt>构建系统</dt><dd>${escapeHTML(session.executed_build_system ?? session.selected_build_system ?? "未记录")}</dd></dl><h3>编译命令</h3>${commands}<h3>产物清单</h3><div class="table-wrap"><table><thead><tr><th>路径</th><th>类型</th><th>大小（B）</th><th>SHA-256</th></tr></thead><tbody>${artifacts}</tbody></table></div><h3>验证与重放</h3>${htmlDetails(`候选验证 · ${session.verification?.status ?? "未记录"}`, htmlPre(session.verification), "candidate-verification", session.verification?.status === "failed")}${replays}${htmlDetails("Session API 原始响应", htmlPre(session), "raw-session")}</section>`;
}

export function formatThreadAsHTML(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
): string {
  const tools = associateTools(messages);
  const messageHTML: string[] = [];
  for (const message of messages) {
    if (message.type === "human") {
      const content = extractContentFromMessage(message);
      if (content)
        messageHTML.push(
          `<section class="message human"><h2>用户</h2>${htmlPre(content, "message-text")}</section>`,
        );
      continue;
    }
    if (message.type !== "ai") continue;
    const content = extractContentFromMessage(message);
    const reasoning = extractReasoningContentFromMessage(message)?.trim();
    const associations = tools.byMessage.get(message) ?? [];
    if (!content && !reasoning && !associations.length) continue;
    const parts = ['<section class="message assistant"><h2>助手</h2>'];
    if (content) parts.push(htmlPre(content, "message-text"));
    if (reasoning)
      parts.push(
        htmlDetails("原始模型推理", htmlPre(reasoning), "raw-reasoning"),
      );
    for (const { call, result } of associations) {
      const body = `<h4>参数</h4>${htmlPre(call.args)}<h4>原始工具结果</h4>${result ? htmlPre(result) : "<p>尚未记录工具结果。</p>"}`;
      parts.push(
        htmlDetails(
          `工具 ${call.name} · ${toolStatus(result)} · ${call.id ?? "无 ID"}`,
          body,
          "tool-call",
        ),
      );
    }
    parts.push("</section>");
    messageHTML.push(parts.join(""));
  }
  for (const message of tools.unmatched) {
    messageHTML.push(
      htmlDetails(
        `未匹配工具结果 · ${message.name ?? "未知工具"} · ${message.tool_call_id ?? "无 ID"}`,
        htmlPre(message),
        "unmatched-tool-result",
      ),
    );
  }
  const todos = thread.values?.todos?.length
    ? htmlDetails("导出时任务状态", htmlPre(thread.values.todos), "todos")
    : "";
  const sessions = compileSessions.map(formatCompileEvidenceHTML).join("");
  const title = titleOfThread(thread);
  const createdAt = thread.created_at
    ? new Date(thread.created_at).toLocaleString()
    : "Unknown";
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>${escapeHTML(title)}</title>
<style>
:root{color-scheme:light dark;--bg:#f6f7f8;--panel:#fff;--text:#202124;--muted:#687076;--line:#d8dde2;--accent:#9a6700;--code:#f0f2f4} @media(prefers-color-scheme:dark){:root{--bg:#151616;--panel:#1f2020;--text:#eee;--muted:#abb2b8;--line:#3c4043;--accent:#e9c665;--code:#292b2d}} *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:0} main{width:min(1120px,calc(100% - 32px));margin:24px auto 64px} header{padding:8px 0 20px;border-bottom:1px solid var(--line)} h1{margin:0 0 8px;font-size:28px} h2{font-size:20px} h3{margin-top:28px;font-size:16px} h4{margin:16px 0 6px}.meta{color:var(--muted)}.toolbar{display:flex;gap:8px;margin-top:16px;position:sticky;top:8px;z-index:2}.toolbar button{border:1px solid var(--line);background:var(--panel);color:var(--text);padding:7px 10px;border-radius:6px;cursor:pointer}.message,.compile-session{margin:18px 0;padding:16px;border:1px solid var(--line);border-radius:8px;background:var(--panel)} details{margin:10px 0;border:1px solid var(--line);border-radius:6px;background:var(--panel)} summary{padding:10px 12px;cursor:pointer;font-weight:600}.details-body{padding:0 12px 12px} pre{max-height:420px;margin:8px 0;padding:12px;overflow:auto;border-radius:6px;background:var(--code);white-space:pre-wrap;overflow-wrap:anywhere}.message-text{max-height:none} code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace} dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 12px} dt{color:var(--muted)} dd{margin:0;overflow-wrap:anywhere}.warning{display:inline-block;margin-left:8px;color:#b42318;font-size:12px}.table-wrap{overflow:auto} table{width:100%;border-collapse:collapse} th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top} td code{overflow-wrap:anywhere}@media(max-width:600px){main{width:min(100% - 20px,1120px);margin-top:10px}.message,.compile-session{padding:12px}dl{grid-template-columns:1fr}dd{margin-bottom:8px}}
</style>
</head>
<body><main>
<header><h1>${escapeHTML(title)}</h1><div class="meta">创建：${escapeHTML(createdAt)} · 导出：${escapeHTML(new Date().toLocaleString())} · Thread ID：<code>${escapeHTML(thread.thread_id)}</code></div><div class="toolbar"><button type="button" data-action="expand">全部展开</button><button type="button" data-action="collapse">全部折叠</button></div></header>
<section aria-label="对话">${messageHTML.join("")}${todos}</section>
${sessions ? `<section aria-label="编译证据"><h1>编译证据</h1>${sessions}</section>` : ""}
</main><script>document.querySelector('[data-action="expand"]').addEventListener('click',()=>document.querySelectorAll('details').forEach((node)=>node.open=true));document.querySelector('[data-action="collapse"]').addEventListener('click',()=>document.querySelectorAll('details').forEach((node)=>node.open=false));</script></body>
</html>`;
}

export function formatThreadAsJSON(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
): string {
  return JSON.stringify(
    {
      title: titleOfThread(thread),
      thread_id: thread.thread_id,
      created_at: thread.created_at,
      exported_at: new Date().toISOString(),
      messages,
      todos: thread.values?.todos,
      artifacts: thread.values?.artifacts,
      compile_sessions: compileSessions,
    },
    null,
    2,
  );
}

function sanitizeFilename(name: string): string {
  return name.replace(/[^\p{L}\p{N}_\- ]/gu, "").trim() || "conversation";
}

export function downloadAsFile(
  content: string,
  filename: string,
  mimeType: string,
) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function exportThreadAsMarkdown(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
) {
  downloadAsFile(
    formatThreadAsMarkdown(thread, messages, compileSessions),
    `${sanitizeFilename(titleOfThread(thread))}.md`,
    "text/markdown;charset=utf-8",
  );
}

export function exportThreadAsHTML(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
) {
  downloadAsFile(
    formatThreadAsHTML(thread, messages, compileSessions),
    `${sanitizeFilename(titleOfThread(thread))}.html`,
    "text/html;charset=utf-8",
  );
}

export function exportThreadAsJSON(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
) {
  downloadAsFile(
    formatThreadAsJSON(thread, messages, compileSessions),
    `${sanitizeFilename(titleOfThread(thread))}.json`,
    "application/json;charset=utf-8",
  );
}
