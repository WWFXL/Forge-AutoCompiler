import type { Message } from "@langchain/langgraph-sdk";

import {
  extractContentFromMessage,
  extractReasoningContentFromMessage,
} from "../messages/utils";

import type { CompileSessionEvidence } from "./export-evidence";
import type { AgentThread } from "./types";
import { titleOfThread } from "./utils";

function formatMessageContent(message: Message): string {
  return extractContentFromMessage(message);
}

function block(content: string, language = "text"): string {
  let length = 3;
  for (const [run] of content.matchAll(/`+/g)) {
    length = Math.max(length, run.length + 1);
  }
  const fence = "`".repeat(length);
  return `${fence}${language}\n${content}\n${fence}`;
}

function formatLog(
  label: string,
  log: { output: string; truncated: boolean },
): string[] {
  return [
    `**${label}${log.truncated ? "（仅保留末尾 16 KiB，原日志已截断）" : ""}**`,
    "",
    block(log.output),
    "",
  ];
}

function formatCompileEvidence(evidence: CompileSessionEvidence): string[] {
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
  for (const [index, command] of session.commands.entries()) {
    lines.push(
      `#### ${index + 1}. ${command.role || command.stage} (${command.command_id})`,
      "",
      `- 目录：${command.workdir}`,
      `- 退出码：${command.exit_code ?? "未记录"}；终止原因：${command.termination ?? "未记录"}；耗时：${command.duration_seconds ?? "未记录"} 秒；超时：${command.timed_out}`,
      "",
      block(command.command, "bash"),
      "",
    );
    const log = command_logs[command.command_id];
    if (log) lines.push(...formatLog("命令输出", log));
  }

  lines.push("### 产物清单", "");
  for (const artifact of session.artifacts) {
    lines.push(
      `- \`${artifact.display_path}\`：${artifact.artifact_type}；${artifact.size_bytes ?? "未记录"} B；SHA-256 \`${artifact.sha256 ?? "未记录"}\`；原路径 \`${artifact.path}\``,
    );
  }
  lines.push(
    "",
    "### 候选验证",
    "",
    block(JSON.stringify(session.verification, null, 2), "json"),
    "",
    "### 干净重放",
    "",
  );
  for (const attempt of session.replay_attempts) {
    lines.push(
      `#### ${attempt.attempt_id}：${attempt.status}`,
      "",
      block(JSON.stringify(attempt, null, 2), "json"),
      "",
    );
    const replayLog = replay_logs[attempt.attempt_id];
    if (replayLog) lines.push(...formatLog("重放日志", replayLog));
    const verificationLog = replay_verification_logs[attempt.attempt_id];
    if (verificationLog)
      lines.push(...formatLog("重放验证日志", verificationLog));
  }
  lines.push(
    "### Session API 原始响应",
    "",
    block(JSON.stringify(session, null, 2), "json"),
    "",
  );
  return lines;
}

export function formatThreadAsMarkdown(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
): string {
  const title = titleOfThread(thread);
  const createdAt = thread.created_at
    ? new Date(thread.created_at).toLocaleString()
    : "Unknown";

  const lines: string[] = [
    `# ${title}`,
    "",
    `*Exported on ${new Date().toLocaleString()} · Created ${createdAt}*`,
    "",
    `Thread ID: \`${thread.thread_id}\``,
    "",
    "---",
    "",
  ];

  const tools = new Map<string, string>();
  for (const message of messages) {
    if (message.type === "ai") {
      for (const call of message.tool_calls ?? []) {
        if (call.id) tools.set(call.id, call.name);
      }
    }
  }

  for (const message of messages) {
    if (message.type === "human") {
      const content = formatMessageContent(message);
      if (content) {
        lines.push("## 用户", "", content, "", "---", "");
      }
    } else if (message.type === "ai") {
      const reasoning = extractReasoningContentFromMessage(message);
      const content = formatMessageContent(message);
      const toolCalls = message.tool_calls ?? [];

      if (!content && !toolCalls.length && !reasoning) continue;

      lines.push("## 助手");

      if (reasoning) {
        lines.push(
          "",
          "<details>",
          "<summary>模型返回的过程内容（原文）</summary>",
          "",
          reasoning,
          "",
          "</details>",
        );
      }

      for (const call of toolCalls) {
        lines.push(
          "",
          `### 调用工具 \`${call.name}\`（${call.id ?? "无 ID"}）`,
          "",
          block(JSON.stringify(call.args, null, 2) ?? "null", "json"),
        );
      }

      if (content) {
        lines.push("", content);
      }

      lines.push("", "---", "");
    } else if (message.type === "tool") {
      lines.push(
        `## 工具结果：\`${tools.get(message.tool_call_id ?? "") ?? message.name ?? "未知工具"}\``,
        "",
        `调用 ID：\`${message.tool_call_id ?? "未记录"}\``,
        "",
        block(JSON.stringify(message, null, 2), "json"),
        "",
        "---",
        "",
      );
    }
  }

  if (thread.values?.todos?.length) {
    lines.push(
      "## 导出时任务状态",
      "",
      block(JSON.stringify(thread.values.todos, null, 2), "json"),
      "",
      "---",
      "",
    );
  }
  if (compileSessions.length) {
    lines.push("# 编译证据", "");
    for (const evidence of compileSessions) {
      lines.push(...formatCompileEvidence(evidence));
    }
  }

  return lines.join("\n").trimEnd() + "\n";
}

export function formatThreadAsJSON(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
): string {
  const exportData = {
    title: titleOfThread(thread),
    thread_id: thread.thread_id,
    created_at: thread.created_at,
    exported_at: new Date().toISOString(),
    messages,
    todos: thread.values?.todos,
    artifacts: thread.values?.artifacts,
    compile_sessions: compileSessions,
  };
  return JSON.stringify(exportData, null, 2);
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
  const markdown = formatThreadAsMarkdown(thread, messages, compileSessions);
  const filename = `${sanitizeFilename(titleOfThread(thread))}.md`;
  downloadAsFile(markdown, filename, "text/markdown;charset=utf-8");
}

export function exportThreadAsJSON(
  thread: AgentThread,
  messages: Message[],
  compileSessions: CompileSessionEvidence[],
) {
  const json = formatThreadAsJSON(thread, messages, compileSessions);
  const filename = `${sanitizeFilename(titleOfThread(thread))}.json`;
  downloadAsFile(json, filename, "application/json;charset=utf-8");
}
