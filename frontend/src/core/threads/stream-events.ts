import type { EventsStreamEvent } from "@langchain/langgraph-sdk";

export type ToolEndEvent = {
  name: string;
  data: unknown;
};

export function createToolEndEventHandler(
  listener: ((event: ToolEndEvent) => void) | undefined,
): ((event: EventsStreamEvent["data"]) => void) | undefined {
  if (!listener) return undefined;

  return (event) => {
    if (event.event !== "on_tool_end") return;
    listener({ name: event.name, data: event.data });
  };
}
