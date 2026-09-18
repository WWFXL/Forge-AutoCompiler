import { ChevronUpIcon, ListTodoIcon } from "lucide-react";
import { useState } from "react";

import type { Todo } from "@/core/todos";
import { cn } from "@/lib/utils";

import {
  QueueItem,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
} from "../ai-elements/queue";

export function TodoList({
  className,
  todos,
  collapsed: controlledCollapsed,
  hidden = false,
  onToggle,
}: {
  className?: string;
  todos: Todo[];
  collapsed?: boolean;
  hidden?: boolean;
  onToggle?: () => void;
}) {
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const isControlled = controlledCollapsed !== undefined;
  const collapsed = isControlled ? controlledCollapsed : internalCollapsed;

  const handleToggle = () => {
    if (isControlled) {
      onToggle?.();
    } else {
      setInternalCollapsed((prev) => !prev);
    }
  };

  if (hidden || todos.length === 0) return null;

  return (
    <div
      className={cn(
        "bg-background text-foreground flex w-full flex-col overflow-hidden rounded-lg border",
        className,
      )}
    >
      <button
        type="button"
        aria-expanded={!collapsed}
        className={cn(
          "bg-accent flex min-h-8 shrink-0 cursor-pointer items-center justify-between px-4 text-sm transition-all duration-300 ease-out",
        )}
        onClick={handleToggle}
      >
        <div className="text-muted-foreground">
          <div className="flex items-center justify-center gap-2">
            <ListTodoIcon className="size-4" />
            <div>To-dos</div>
          </div>
        </div>
        <div>
          <ChevronUpIcon
            className={cn(
              "text-muted-foreground size-4 transition-transform duration-300 ease-out",
              collapsed ? "" : "rotate-180",
            )}
          />
        </div>
      </button>
      {!collapsed && (
        <div
          className={cn("bg-accent flex max-h-28 overflow-y-auto px-2 pb-2")}
        >
          <QueueList className="bg-background mt-0 w-full rounded-md">
            {todos.map((todo, i) => (
              <QueueItem key={i + (todo.content ?? "")}>
                <div className="flex items-center gap-2">
                  <QueueItemIndicator
                    className={
                      todo.status === "in_progress" ? "bg-primary/70" : ""
                    }
                    completed={todo.status === "completed"}
                  />
                  <QueueItemContent
                    className={cn(
                      "line-clamp-none min-w-0 break-words whitespace-normal",
                      todo.status === "in_progress" && "text-primary/70",
                    )}
                    completed={todo.status === "completed"}
                  >
                    {todo.content}
                  </QueueItemContent>
                </div>
              </QueueItem>
            ))}
          </QueueList>
        </div>
      )}
    </div>
  );
}
