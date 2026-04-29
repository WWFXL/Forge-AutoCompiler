"use client";

import { Compass, GitBranch, Package } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";

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
    onCardClick?.(text);
  };

  const cardData = [
    {
      Icon: Compass,
      title: "探索 Forge 工作流",
      subtitle: "了解双轨 Agent 架构如何协同工作，以及系统核心自动化编译能力。",
      text: "你好！请向我详细介绍 Forge 的核心架构（Lead 与 Sub Agent 是如何协同的），以及你能帮我自动化编译什么类型的 C/C++ 项目？",
    },
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
    </div>
  );
}
