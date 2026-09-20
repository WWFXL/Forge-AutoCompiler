import assert from "node:assert/strict";
import test from "node:test";

import type { Message } from "@langchain/langgraph-sdk";

const { convertToProcessingSteps } = await import(
  new URL("./processing-steps.ts", import.meta.url).href
);

void test("带工具调用的消息同时保留真实正文、原始推理和工具事实", () => {
  const messages = [
    {
      id: "assistant-1",
      type: "ai",
      content: "编译会话已准备好，接下来克隆仓库。",
      additional_kwargs: {
        reasoning_content: "Session prepared. Now clone the repository.",
      },
      tool_calls: [
        {
          id: "call-1",
          name: "clone_repository",
          args: {},
          type: "tool_call",
        },
      ],
    },
    {
      id: "tool-1",
      type: "tool",
      name: "clone_repository",
      tool_call_id: "call-1",
      content: "Repository cloned successfully.",
    },
  ] as Message[];

  assert.deepEqual(convertToProcessingSteps(messages), [
    {
      id: "assistant-1-content",
      messageId: "assistant-1",
      type: "narration",
      content: "编译会话已准备好，接下来克隆仓库。",
    },
    {
      id: "assistant-1-reasoning",
      messageId: "assistant-1",
      type: "reasoning",
      reasoning: "Session prepared. Now clone the repository.",
    },
    {
      id: "call-1",
      messageId: "assistant-1",
      type: "toolCall",
      name: "clone_repository",
      args: {},
      result: "Repository cloned successfully.",
    },
  ]);
});

void test("没有真实正文时不创建 narration fallback", () => {
  const messages = [
    {
      id: "assistant-2",
      type: "ai",
      content: "",
      additional_kwargs: { reasoning_content: "Need to inspect the build." },
      tool_calls: [
        {
          id: "call-2",
          name: "identify_build_system",
          args: {},
          type: "tool_call",
        },
      ],
    },
  ] as Message[];

  const steps = convertToProcessingSteps(messages);
  assert.deepEqual(
    steps.map((step: { type: string }) => step.type),
    ["reasoning", "toolCall"],
  );
  assert.equal(
    steps.some((step: { type: string }) => step.type === "narration"),
    false,
  );
});
