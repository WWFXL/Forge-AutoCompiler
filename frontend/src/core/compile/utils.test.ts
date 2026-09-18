import assert from "node:assert/strict";
import test from "node:test";

import type { Message } from "@langchain/langgraph-sdk";

const { findCompileSessionForTask } = await import(
  new URL("./utils.ts", import.meta.url).href
);

const ai = (id: string, name: string): Message =>
  ({
    type: "ai",
    content: "",
    tool_calls: [{ id, name, args: {} }],
  }) as Message;
const tool = (id: string, content: string): Message =>
  ({ type: "tool", content, tool_call_id: id }) as Message;

void test("binds historical tasks to their own successful prepare without tool name", () => {
  const messages = [
    ai("p1", "prepare_compile_session"),
    tool("p1", "Compile session prepared. session_id=first, container_id=abc"),
    ai("t1", "task"),
    ai("p2", "prepare_compile_session"),
    tool("p2", '{"session_id":"second"}'),
    ai("t2", "task"),
  ];
  assert.equal(findCompileSessionForTask(messages, "t1"), "first");
  assert.equal(findCompileSessionForTask(messages, "t2"), "second");
});

void test("failed or pending prepare never reuses the previous session", () => {
  const messages = [
    ai("p1", "prepare_compile_session"),
    tool("p1", "session_id=first"),
    ai("p2", "prepare_compile_session"),
    tool("p2", "Error: unable to prepare"),
    ai("t", "task"),
  ];
  assert.equal(findCompileSessionForTask(messages, "t"), undefined);
  assert.equal(
    findCompileSessionForTask(
      messages.slice(0, 3).concat(ai("t", "task")),
      "t",
    ),
    undefined,
  );
});

void test("does not bind unknown tasks, unrelated results or future prepare", () => {
  assert.equal(
    findCompileSessionForTask(
      [
        ai("t", "task"),
        ai("p", "prepare_compile_session"),
        tool("p", "session_id=later"),
      ],
      "t",
    ),
    undefined,
  );
  assert.equal(
    findCompileSessionForTask(
      [ai("x", "other"), tool("x", "session_id=wrong"), ai("t", "task")],
      "t",
    ),
    undefined,
  );
  assert.equal(findCompileSessionForTask([], "missing"), undefined);
});

void test("accepts text blocks but rejects unsafe identifiers", () => {
  const message = {
    type: "tool",
    tool_call_id: "p",
    content: [{ type: "text", text: "session_id=valid-id" }],
  } as Message;
  assert.equal(
    findCompileSessionForTask(
      [ai("p", "prepare_compile_session"), message, ai("t", "task")],
      "t",
    ),
    "valid-id",
  );
  assert.equal(
    findCompileSessionForTask(
      [
        ai("p", "prepare_compile_session"),
        tool("p", '{"session_id":"../private"}'),
        ai("t", "task"),
      ],
      "t",
    ),
    undefined,
  );
});

void test("late results from an older prepare cannot overwrite the current binding", () => {
  const messages = [
    ai("p1", "prepare_compile_session"),
    ai("p2", "prepare_compile_session"),
    tool("p2", "session_id=current"),
    tool("p1", "session_id=old"),
    ai("t", "task"),
  ];
  assert.equal(findCompileSessionForTask(messages, "t"), "current");
});
