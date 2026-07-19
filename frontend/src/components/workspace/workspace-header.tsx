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
            <div className="bg-forge-gold/10 border-forge-gold/30 glow-gold flex h-8 w-8 items-center justify-center rounded border">
              <Sparkles className="text-forge-gold h-4 w-4" />
            </div>
            <SidebarTrigger className="hidden pl-2 group-hover/workspace-header:block" />
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <div className="ml-2 flex items-center gap-2">
              <div className="bg-forge-gold/10 border-forge-gold/30 glow-gold flex h-8 w-8 items-center justify-center rounded border">
                <Sparkles className="text-forge-gold h-5 w-5" />
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
            className="bg-forge-gold/10 text-forge-gold hover:bg-forge-gold/20 hover:text-forge-gold border-forge-gold/20 border"
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
