import assert from "node:assert/strict";
import test from "node:test";

const { buildRunContext, getResolvedMode } = await import(
  new URL("./run-context.ts", import.meta.url).href
);

void test("无 thinking 能力仍可选择 Pro/Ultra，只有 Thinking 降级", () => {
  for (const mode of ["flash", "pro", "ultra"]) {
    assert.equal(getResolvedMode(mode, false), mode);
  }
  assert.equal(getResolvedMode("thinking", false), "flash");
  assert.equal(getResolvedMode(undefined, false), "flash");
  assert.equal(getResolvedMode(undefined, true), "pro");
});

void test("规划、委派与 thinking 能力分别控制", () => {
  for (const supportsThinking of [false, true]) {
    for (const mode of ["flash", "thinking", "pro", "ultra"]) {
      const result = buildRunContext(
        { mode, model_name: "test" },
        { supports_thinking: supportsThinking },
        "thread",
      );
      assert.equal(result.is_plan_mode, mode === "pro" || mode === "ultra");
      assert.equal(result.subagent_enabled, mode === "ultra");
      assert.equal(
        result.thinking_enabled,
        mode !== "flash" && supportsThinking,
      );
      assert.equal(result.thread_id, "thread");
      assert.equal(result.model_name, "test");
    }
  }
});

void test("不支持 reasoning effort 时清除历史与额外上下文残留", () => {
  for (const model of [undefined, {}, { supports_reasoning_effort: false }]) {
    const result = buildRunContext(
      { mode: "ultra", reasoning_effort: "high" },
      model,
      "thread",
      {
        reasoning_effort: "medium",
        thinking_enabled: true,
        subagent_enabled: false,
      },
    );
    assert.equal(Object.hasOwn(result, "reasoning_effort"), false);
    assert.equal(result.thinking_enabled, false);
    assert.equal(result.subagent_enabled, true);
  }
});

void test("支持的模型保留默认 effort 与用户覆盖", () => {
  const model = { supports_thinking: true, supports_reasoning_effort: true };
  for (const [mode, effort] of [
    ["thinking", "low"],
    ["pro", "medium"],
    ["ultra", "high"],
  ]) {
    assert.equal(
      buildRunContext({ mode }, model, "thread").reasoning_effort,
      effort,
    );
  }
  assert.equal(
    buildRunContext(
      { mode: "ultra", reasoning_effort: "minimal" },
      model,
      "thread",
    ).reasoning_effort,
    "minimal",
  );
  assert.equal(
    Object.hasOwn(
      buildRunContext({ mode: "flash" }, model, "thread"),
      "reasoning_effort",
    ),
    false,
  );
});
