"use client";

import { Container, Package } from "lucide-react";

import { cn } from "@/lib/utils";

import { Section } from "../section";

function TerminalMockup() {
  const logs = [
    { agent: "LeadAgent", text: "Analyzed CMakeLists.txt", status: null },
    { agent: "LeadAgent", text: "Resolved dep tree: 42 nodes", status: null },
    { agent: "ExecAgent", text: "Sandboxed build started", status: null },
    { agent: "ExecAgent", text: "Compilation successful", status: "ok" },
    { agent: "ExecAgent", text: "CCache hit rate: 87%", status: "ok" },
  ];

  return (
    <div className="border-forge-border overflow-hidden rounded-xl border bg-[#0d0d0d] font-mono text-sm">
      <div className="border-forge-border flex items-center gap-2 border-b bg-[#1a1a1a] px-4 py-2">
        <div className="h-3 w-3 rounded-full bg-rose-400/50" />
        <div className="h-3 w-3 rounded-full bg-amber-400/50" />
        <div className="h-3 w-3 rounded-full bg-emerald-400/50" />
        <span className="ml-2 text-xs text-gray-500">forge-agent-log</span>
      </div>
      <div className="space-y-1.5 p-4">
        {logs.map((log, i) => (
          <div key={i} className="flex gap-2 text-gray-400">
            <span className="text-orange-400">[{log.agent}]</span>
            <span>{log.text}</span>
            {log.status === "ok" && (
              <span className="ml-2 text-emerald-400">[OK]</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function FeatureCard({
  icon,
  label,
  title,
  description,
}: {
  icon: React.ReactNode;
  label: string;
  title: string;
  description: string;
}) {
  return (
    <div className="bg-forge-card border-forge-border rounded-2xl border p-8 transition-all hover:translate-y-[-4px] hover:border-white/20">
      <div className="mb-6 inline-flex rounded-lg bg-white/5 p-2 text-orange-400">
        {icon}
      </div>
      <div className="mb-3 font-mono text-xs tracking-widest text-gray-500 uppercase">
        {label}
      </div>
      <h4 className="mb-3 text-xl font-bold text-white">{title}</h4>
      <p className="text-sm leading-relaxed text-gray-400">{description}</p>
    </div>
  );
}

export function WhatsNewSection({ className }: { className?: string }) {
  return (
    <Section
      className={cn("", className)}
      title="Next-Gen C/C++ Build Pipeline"
      subtitle="基于 Docker 与双轨 Agent 协同的全自动编译引擎"
    >
      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
        {/* Card 1: Terminal Mockup */}
        <div className="bg-forge-card border-forge-border rounded-2xl border p-6 transition-all hover:translate-y-[-4px] hover:border-white/20">
          <div className="mb-4 font-mono text-xs tracking-widest text-orange-400 uppercase">
            Dual-Agent 协同架构
          </div>
          <TerminalMockup />
          <p className="mt-4 text-sm leading-relaxed text-gray-400">
            架构师 Agent 负责解析 CMake 与依赖树，执行 Agent
            在独立沙盒中完成排错与编译。
          </p>
        </div>

        {/* Card 2: Docker Sandbox */}
        <FeatureCard
          icon={<Container className="h-5 w-5" />}
          label="纯净 Docker 沙盒"
          title="隔离环境 · 极致性能"
          description="每次任务在独立容器中执行，挂载宿主机持久化 CCache 释放极致编译性能。"
        />

        {/* Card 3: Dependency Hell */}
        <FeatureCard
          icon={<Package className="h-5 w-5" />}
          label="终结依赖地狱"
          title="自动嗅探 · 原生集成"
          description="自动嗅探环境，原生处理复杂的 Git Submodules，深度集成 Conan / vcpkg。"
        />
      </div>
    </Section>
  );
}
