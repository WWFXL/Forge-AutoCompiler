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
    <div className="bg-[#0d0d0d] border border-forge-border rounded-xl overflow-hidden font-mono text-sm">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-forge-border bg-[#1a1a1a]">
        <div className="w-3 h-3 rounded-full bg-rose-400/50" />
        <div className="w-3 h-3 rounded-full bg-amber-400/50" />
        <div className="w-3 h-3 rounded-full bg-emerald-400/50" />
        <span className="ml-2 text-xs text-gray-500">forge-agent-log</span>
      </div>
      <div className="p-4 space-y-1.5">
        {logs.map((log, i) => (
          <div key={i} className="flex gap-2 text-gray-400">
            <span className="text-orange-400">[{log.agent}]</span>
            <span>{log.text}</span>
            {log.status === "ok" && (
              <span className="text-emerald-400 ml-2">[OK]</span>
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
    <div className="bg-forge-card border border-forge-border rounded-2xl p-8 transition-all hover:border-white/20 hover:translate-y-[-4px]">
      <div className="inline-flex p-2 rounded-lg bg-white/5 mb-6 text-orange-400">
        {icon}
      </div>
      <div className="text-xs font-mono text-gray-500 uppercase tracking-widest mb-3">
        {label}
      </div>
      <h4 className="text-xl font-bold text-white mb-3">{title}</h4>
      <p className="text-gray-400 leading-relaxed text-sm">{description}</p>
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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
        {/* Card 1: Terminal Mockup */}
        <div className="bg-forge-card border border-forge-border rounded-2xl p-6 transition-all hover:border-white/20 hover:translate-y-[-4px]">
          <div className="text-xs font-mono text-orange-400 uppercase tracking-widest mb-4">
            Dual-Agent 协同架构
          </div>
          <TerminalMockup />
          <p className="mt-4 text-gray-400 text-sm leading-relaxed">
            架构师 Agent 负责解析 CMake 与依赖树，执行 Agent 在独立沙盒中完成排错与编译。
          </p>
        </div>

        {/* Card 2: Docker Sandbox */}
        <FeatureCard
          icon={<Container className="w-5 h-5" />}
          label="纯净 Docker 沙盒"
          title="隔离环境 · 极致性能"
          description="每次任务在独立容器中执行，挂载宿主机持久化 CCache 释放极致编译性能。"
        />

        {/* Card 3: Dependency Hell */}
        <FeatureCard
          icon={<Package className="w-5 h-5" />}
          label="终结依赖地狱"
          title="自动嗅探 · 原生集成"
          description="自动嗅探环境，原生处理复杂的 Git Submodules，深度集成 Conan / vcpkg。"
        />
      </div>
    </Section>
  );
}
