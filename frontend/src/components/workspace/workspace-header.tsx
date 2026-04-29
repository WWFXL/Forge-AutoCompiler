"use client";

import { MessageSquarePlus, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { env } from "@/env";
import { cn } from "@/lib/utils";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { t } = useI18n();
  const { state } = useSidebar();
  const pathname = usePathname();
  return (
    <>
      <div
        className={cn(
          "group/workspace-header flex h-14 flex-col justify-center px-2",
          className,
        )}
      >
        {state === "collapsed" ? (
          <div className="group-has-data-[collapsible=icon]/sidebar-wrapper:-translate-y flex w-full cursor-pointer items-center justify-center">
            <div className="flex items-center justify-center w-8 h-8 bg-forge-gold/10 border border-forge-gold/30 rounded glow-gold">
              <Sparkles className="w-4 h-4 text-forge-gold" />
            </div>
            <SidebarTrigger className="hidden pl-2 group-hover/workspace-header:block" />
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 ml-2">
              <div className="w-8 h-8 bg-forge-gold/10 border border-forge-gold/30 rounded flex items-center justify-center glow-gold">
                <Sparkles className="w-5 h-5 text-forge-gold" />
              </div>
              <span className="font-display font-bold text-white">Forge</span>
            </div>
            <SidebarTrigger />
          </div>
        )}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new"}
            asChild
            className="bg-forge-gold/10 text-forge-gold hover:bg-forge-gold/20 hover:text-forge-gold border border-forge-gold/20"
          >
            <Link href="/workspace/chats/new">
              <MessageSquarePlus size={16} />
              <span>{t.sidebar.newChat}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
