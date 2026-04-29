"use client";

import { useState } from "react";
import { StarFilledIcon, GitHubLogoIcon } from "@radix-ui/react-icons";
import Link from "next/link";
import { motion } from "motion/react";
import { Sparkles, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { NumberTicker } from "@/components/ui/number-ticker";
import type { Locale } from "@/core/i18n/locale";
import { cn } from "@/lib/utils";

export type HeaderProps = {
  className?: string;
  homeURL?: string;
  locale?: Locale;
};

const navItems = [
  { label: "Models", href: "#", isActive: true },
  { label: "Research", href: "#" },
  { label: "Changelog", href: "#" },
  { label: "Docs", href: "#" },
  { label: "Blog", href: "#" },
];

export function Header({ className, homeURL, locale }: HeaderProps) {
  const [activeItem, setActiveItem] = useState("Models");

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 z-50 border-b border-forge-border bg-forge-bg/80 backdrop-blur-md",
        className,
      )}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2 cursor-pointer">
            <div className="w-8 h-8 bg-forge-gold/10 border border-forge-gold/30 rounded flex items-center justify-center glow-gold">
              <Sparkles className="w-5 h-5 text-forge-gold" />
            </div>
            <span className="font-display font-bold text-xl tracking-tight text-white">
              Forge
            </span>
          </div>

          {/* Navigation */}
          <div className="hidden md:flex items-center gap-6 relative">
            {navItems.map((item) => (
              <a
                key={item.label}
                href={item.href}
                onClick={() => setActiveItem(item.label)}
                className={cn(
                  "text-sm font-medium transition-colors relative py-4",
                  activeItem === item.label
                    ? "text-forge-gold"
                    : "text-gray-400 hover:text-white",
                )}
              >
                {item.label}
                {activeItem === item.label && (
                  <motion.div
                    layoutId="nav-underline"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-forge-gold"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
              </a>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            asChild
            className="hidden sm:flex items-center gap-2 text-gray-400 hover:text-white border border-forge-border hover:bg-forge-border/50"
          >
            <a
              href="https://github.com/your-org/forge"
              target="_blank"
              rel="noopener noreferrer"
            >
              <GitHubLogoIcon className="size-4" />
              Star on GitHub
            </a>
          </Button>
          <Button
            asChild
            className="bg-forge-gold text-black hover:brightness-110 active:scale-95 font-bold"
          >
            <a href={homeURL ?? "/"}>
              Get Started
              <ChevronRight className="w-4 h-4 ml-1" />
            </a>
          </Button>
        </div>
      </div>
    </header>
  );
}
