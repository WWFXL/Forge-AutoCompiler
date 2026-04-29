"use client";

import { motion, AnimatePresence } from "framer-motion";
import { GitBranch, Package, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

let waved = false;

export function Welcome({
  className,
  mode,
  onCardClick,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
  onCardClick?: (text: string) => void;
}) {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const isUltra = useMemo(() => mode === "ultra", [mode]);
  const [dismissed, setDismissed] = useState(false);
  const colors = useMemo(() => {
    if (isUltra) {
      return ["#efefbb", "#e9c665", "#e3a812"];
    }
    return ["var(--color-foreground)"];
  }, [isUltra]);

  useEffect(() => {
    waved = true;
  }, []);

  const handleCardClick = (text: string) => {
    setDismissed(true);
    onCardClick?.(text);
  };

  const cardData = [
    {
      Icon: Package,
      title: t.welcome.actionCards.cmakeTitle,
      subtitle: t.welcome.actionCards.cmakeSubtitle,
      text: "克隆并编译标准现代 CMake 项目：https://github.com/fmtlib/fmt",
    },
    {
      Icon: GitBranch,
      title: t.welcome.actionCards.grpcTitle,
      subtitle: t.welcome.actionCards.grpcSubtitle,
      text: "克隆并深度解析编译 gRPC 项目：https://github.com/grpc/grpc，请注意处理子模块。",
    },
    {
      Icon: Trash2,
      title: t.welcome.actionCards.ccacheTitle,
      subtitle: t.welcome.actionCards.ccacheSubtitle,
      text: "执行系统维护：清理宿主机挂载的 CCache 缓存。",
    },
  ];

  if (searchParams.get("mode") === "skill") {
    return (
      <div
        className={cn(
          "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
          className,
        )}
      >
        <div className="text-2xl font-bold">
          <div className="flex items-center gap-2">
            <div className={cn("inline-block", !waved ? "animate-wave" : "")}>
              ✨
            </div>
            <AuroraText colors={colors}>{t.welcome.createYourOwnSkill}</AuroraText>
          </div>
        </div>
        <div className="text-muted-foreground text-sm">
          <pre className="font-sans whitespace-pre">
            {t.welcome.createYourOwnSkillDescription}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
        className,
      )}
    >
      <AnimatePresence mode="wait">
        {!dismissed && (
          <motion.div
            key="forge-hero"
            initial={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="flex w-full flex-col items-center"
          >
            {/* Hero Section */}
            <div className="forge-hero">
              <div className="forge-hero-icon">🔨</div>
              <h1 className="forge-hero-title">
                <AuroraText colors={["#FFB800", "#FF8C00"]}>
                  {t.welcome.greeting}
                </AuroraText>
              </h1>
              <p className="forge-hero-subtitle">{t.welcome.description}</p>
            </div>

            {/* Action Cards */}
            <div className="forge-cards">
              {cardData.map((card) => (
                <div
                  key={card.text}
                  className="forge-card"
                  onClick={() => handleCardClick(card.text)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      handleCardClick(card.text);
                    }
                  }}
                >
                  <card.Icon className="forge-card-icon" />
                  <div className="forge-card-title">{card.title}</div>
                  <div className="forge-card-subtitle">{card.subtitle}</div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
