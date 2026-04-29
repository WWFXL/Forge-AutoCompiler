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
        "fixed top-0 left-0 right-0 z-50 border-b border-forge-border bg-forge-bg/80 backdrop-blur-md",
        className,
      )}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2 cursor-pointer">
          <div className="w-8 h-8 bg-forge-gold/10 border border-forge-gold/30 rounded flex items-center justify-center glow-gold">
            <Sparkles className="w-5 h-5 text-forge-gold" />
          </div>
          <span className="font-display font-bold text-xl tracking-tight text-white">
            Forge
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            asChild
            className="text-gray-400 hover:text-white border border-forge-border hover:bg-forge-border/50"
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
            className="bg-orange-600 hover:bg-orange-500 text-white border border-orange-400/50 shadow-[0_0_20px_rgba(234,88,12,0.2)] transition-all active:scale-95 font-bold"
          >
            <a href={homeURL ?? "/workspace"}>
              进入工作台
              <ChevronRight className="w-4 h-4 ml-1" />
            </a>
          </Button>
        </div>
      </div>
    </header>
  );
}
