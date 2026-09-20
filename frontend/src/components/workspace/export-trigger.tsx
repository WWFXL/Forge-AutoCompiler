"use client";

import { Download, FileJson, FileText } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { getAPIClient } from "@/core/api";
import { findCompileSessionIds } from "@/core/compile/utils";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import {
  exportThreadAsJSON,
  exportThreadAsMarkdown,
} from "@/core/threads/export";
import { loadCompileEvidence } from "@/core/threads/export-evidence";
import type { AgentThread } from "@/core/threads/types";

import { useThread } from "./messages/context";
import { Tooltip } from "./tooltip";

export function ExportTrigger({ threadId }: { threadId: string }) {
  const { t } = useI18n();
  const { thread } = useThread();
  const [exporting, setExporting] = useState(false);

  const messages = thread.messages;

  const handleExport = useCallback(
    async (format: "markdown" | "json") => {
      if (messages.length === 0) {
        toast.error(t.conversation.noMessages);
        return;
      }
      setExporting(true);
      try {
        const metadata =
          await getAPIClient().threads.get<AgentThread["values"]>(threadId);
        const agentThread: AgentThread = {
          ...metadata,
          values: thread.values,
        };
        const evidence = await loadCompileEvidence(
          getBackendBaseURL(),
          threadId,
          findCompileSessionIds(messages),
        );
        if (format === "markdown") {
          exportThreadAsMarkdown(agentThread, messages, evidence);
        } else {
          exportThreadAsJSON(agentThread, messages, evidence);
        }
        toast.success(t.common.exportSuccess);
      } catch (error) {
        toast.error(t.common.exportFailed, {
          description: error instanceof Error ? error.message : undefined,
        });
      } finally {
        setExporting(false);
      }
    },
    [messages, thread.values, threadId, t],
  );

  if (messages.length === 0) {
    return null;
  }

  return (
    <DropdownMenu>
      <Tooltip content={t.common.export}>
        <DropdownMenuTrigger asChild>
          <Button
            className="text-muted-foreground hover:text-foreground"
            variant="ghost"
            disabled={exporting}
          >
            <Download />
            {t.common.export}
          </Button>
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => handleExport("markdown")}>
          <FileText className="text-muted-foreground" />
          <span>{t.common.exportAsMarkdown}</span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => handleExport("json")}>
          <FileJson className="text-muted-foreground" />
          <span>{t.common.exportAsJSON}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
