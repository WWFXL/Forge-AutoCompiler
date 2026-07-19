"use client";

import {
  Terminal,
  Cpu,
  ArrowRight,
  BrainCircuit,
  Box,
  Network,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Hero({ className }: { className?: string }) {
  return (
    <section
      className={cn(
        "relative min-h-screen overflow-hidden pt-32 pb-20",
        className,
      )}
    >
      {/* Grid backgrounds */}
      <div className="bg-grid absolute inset-0 opacity-20" />
      <div className="bg-grid-fine absolute inset-0 opacity-40" />
      {/* Ambient forge glow */}
      <div className="pointer-events-none absolute top-1/4 left-1/2 -z-10 h-[400px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-orange-600/10 blur-[120px]" />

      <div className="relative mx-auto max-w-7xl px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-orange-500/20 bg-orange-600/10 px-3 py-1 font-mono text-xs font-bold tracking-widest text-orange-400 uppercase">
            🔥 Forge Agent Core Active
          </div>

          {/* Heading */}
          <h1 className="font-display mb-6 text-5xl leading-tight font-bold tracking-tighter text-white md:text-7xl lg:text-8xl">
            Autopilot for C/C++ Builds <br />
            <span className="text-forge-gold text-glow-gold">with Forge</span>
          </h1>

          {/* Description */}
          <p className="mx-auto mb-12 max-w-2xl text-lg leading-relaxed text-gray-400 md:text-xl">
            基于 Docker 隔离与双轨 Agent
            协同的端到端编译引擎。彻底告别依赖地狱，专注代码锻造。
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link href="/workspace">
              <Button
                size="lg"
                className="group h-14 w-full rounded-xl border border-orange-400/50 bg-orange-600 px-8 font-bold text-white shadow-[0_0_30px_rgba(234,88,12,0.3)] transition-all hover:scale-105 hover:bg-orange-500 active:scale-95 sm:w-auto"
              >
                进入工作台 (Enter Workspace)
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
            <Button
              variant="outline"
              size="lg"
              asChild
              className="h-14 w-full rounded-xl border-white/10 bg-white/5 px-8 font-bold text-white transition-all hover:border-white/20 hover:bg-white/10 active:scale-95 sm:w-auto"
            >
              <a
                href="https://github.com/your-org/forge"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2"
              >
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                View Source
              </a>
            </Button>
          </div>
        </motion.div>
      </div>

      {/* Terminal and Skills Grid */}
      <div className="mx-auto mt-24 max-w-6xl px-6">
        <div className="grid gap-6 md:grid-cols-[1.5fr,1fr]">
          {/* Sandbox Terminal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2, duration: 0.8 }}
            className="bg-forge-card border-forge-border flex h-[400px] flex-col overflow-hidden rounded-2xl border shadow-2xl"
          >
            <div className="border-forge-border flex items-center justify-between border-b p-5">
              <div className="flex items-center gap-3">
                <span className="font-display text-sm font-bold text-white">
                  Sandbox Terminal
                </span>
              </div>
              <Terminal className="h-5 w-5 text-cyan-400" />
            </div>

            <div className="flex-1 overflow-hidden p-8 font-mono text-sm leading-relaxed">
              <div className="mb-6 flex gap-2">
                <div className="h-3 w-3 rounded-full bg-rose-400/50" />
                <div className="h-3 w-3 rounded-full bg-amber-400/50" />
                <div className="h-3 w-3 rounded-full bg-emerald-400/50" />
              </div>

              <div className="space-y-1">
                <p className="flex gap-2 text-gray-500">
                  <span className="text-forge-gold">&gt;</span> forge init
                  project_alpha
                </p>
                <p className="ml-4 font-medium text-gray-400 italic">
                  Initializing neural pathways...
                </p>
                <p className="ml-4 text-gray-400">
                  Allocating cognitive resources...{" "}
                  <span className="text-emerald-400">[OK]</span>
                </p>
                <p className="flex gap-2 text-white">
                  <span className="text-forge-gold">&gt;</span>{" "}
                  <span className="text-cyan-400">Ready for input</span>
                  <span className="inline-block h-5 w-2 animate-pulse bg-cyan-400" />
                </p>
              </div>
            </div>
          </motion.div>

          {/* Cognitive Skills Card */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.8 }}
            className="bg-forge-card border-forge-border hover:border-forge-gold/30 hover:bg-forge-gold/[0.02] group flex flex-col items-center justify-center rounded-2xl border p-8 text-center transition-all"
          >
            <div className="bg-forge-gold/5 border-forge-gold/20 glow-gold ring-forge-gold/5 mb-10 flex h-20 w-20 items-center justify-center rounded-full border ring-4 transition-transform group-hover:scale-110">
              <BrainCircuit className="text-forge-gold h-10 w-10" />
            </div>
            <h3 className="font-display mb-4 text-2xl font-bold text-white">
              Cognitive Skills
            </h3>
            <p className="max-w-xs leading-relaxed text-gray-400">
              Rapid adaptation and execution modules loading seamlessly.
            </p>
          </motion.div>
        </div>

        {/* Feature Grid */}
        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-4">
          <FeatureCard
            icon={<Cpu className="h-5 w-5" />}
            title="双轨 Agent 协同"
            desc="架构师 Agent 解析构建系统与依赖树，执行 Agent 负责沙盒内排错，思维链全程透明。"
            color="text-orange-500"
          />
          <FeatureCard
            icon={<Box className="h-5 w-5" />}
            title="纯净 Docker 沙盒"
            desc="任务在独立拉取的干净容器中执行，挂载持久化 CCache，杜绝环境污染。"
            color="text-blue-500"
          />
          <FeatureCard
            icon={<Network className="h-5 w-5" />}
            title="终结依赖地狱"
            desc="自动嗅探环境，处理复杂的 Git Submodules，深度集成现代 C++ 包管理器。"
            color="text-green-500"
          />
          <div className="bg-forge-card border-forge-border group flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border p-8 transition-all hover:border-white/20">
            <div className="flex h-12 w-12 items-center justify-center rounded-full">
              <ArrowRight className="h-8 w-8 transform text-gray-500 transition-all group-hover:translate-x-1 group-hover:text-white" />
            </div>
            <span className="text-sm font-bold text-gray-500 group-hover:text-white">
              See all updates
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function FeatureCard({
  icon,
  title,
  desc,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  color: string;
}) {
  return (
    <div className="bg-forge-card border-forge-border rounded-2xl border p-8 transition-all hover:translate-y-[-4px] hover:border-white/20">
      <div
        className={cn(
          "mb-6 inline-flex rounded-lg bg-white/5 p-2 opacity-80",
          color,
        )}
      >
        {icon}
      </div>
      <h4 className="mb-2 text-lg font-bold text-white">{title}</h4>
      <p className="text-sm leading-relaxed font-medium text-gray-500">
        {desc}
      </p>
    </div>
  );
}
