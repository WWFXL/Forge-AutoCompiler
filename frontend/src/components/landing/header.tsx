"use client";

import { GitHubLogoIcon } from "@radix-ui/react-icons";
import { Sparkles, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Locale } from "@/core/i18n/locale";
import { cn } from "@/lib/utils";

export type HeaderProps = {
  className?: string;
  homeURL?: string;
  locale?: Locale;
};

export function Header({ className, homeURL, locale: _locale }: HeaderProps) {
  return (
    <header
      className={cn(
        "border-forge-border bg-forge-bg/80 fixed top-0 right-0 left-0 z-50 border-b backdrop-blur-md",
        className,
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        {/* Logo */}
        <div className="flex cursor-pointer items-center gap-2">
          <div className="bg-forge-gold/10 border-forge-gold/30 glow-gold flex h-8 w-8 items-center justify-center rounded border">
            <Sparkles className="text-forge-gold h-5 w-5" />
          </div>
          <span className="font-display text-xl font-bold tracking-tight text-white">
            Forge
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            asChild
            className="border-forge-border hover:bg-forge-border/50 border text-gray-400 hover:text-white"
          >
            <a
              href="https://github.com/your-org/forge"
              target="_blank"
              rel="noopener noreferrer"
            >
              <GitHubLogoIcon className="size-4" />
            </a>
          </Button>
          <Button
            asChild
            className="border border-orange-400/50 bg-orange-600 font-bold text-white shadow-[0_0_20px_rgba(234,88,12,0.2)] transition-all hover:bg-orange-500 active:scale-95"
          >
            <a href={homeURL ?? "/workspace"}>
              进入工作台
              <ChevronRight className="ml-1 h-4 w-4" />
            </a>
          </Button>
        </div>
      </div>
    </header>
  );
}
