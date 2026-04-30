"use client";

import { BotIcon, MessagesSquare } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  const isChatsActive = pathname.startsWith("/workspace/chats") && !pathname.endsWith("/new");
  const isAgentsActive = pathname.startsWith("/workspace/agents");
  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton isActive={isChatsActive} asChild>
            <Link
              className={cn(
                isChatsActive ? "text-forge-gold" : "text-muted-foreground"
              )}
              href="/workspace/chats"
            >
              <MessagesSquare />
              <span>{t.sidebar.chats}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton isActive={isAgentsActive} asChild>
            <Link
              className={cn(
                isAgentsActive ? "text-forge-gold" : "text-muted-foreground"
              )}
              href="/workspace/agents"
            >
              <BotIcon />
              <span>{t.sidebar.agents}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  );
}
