"use client";

import { Terminal, Shield, Cpu, Zap, ArrowRight, BrainCircuit, Sparkles, Box, Network } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Hero({ className }: { className?: string }) {
  return (
    <section className={cn("relative pt-32 pb-20 overflow-hidden min-h-screen", className)}>
      {/* Grid backgrounds */}
      <div className="bg-grid absolute inset-0 opacity-20" />
      <div className="bg-grid-fine absolute inset-0 opacity-40" />
      {/* Ambient forge glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-orange-600/10 rounded-full blur-[120px] pointer-events-none -z-10" />

      <div className="max-w-7xl mx-auto px-6 relative text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-600/10 border border-orange-500/20 text-orange-400 text-xs font-bold tracking-widest uppercase mb-8 font-mono">
            🔥 Forge Agent Core Active
          </div>

          {/* Heading */}
          <h1 className="font-display font-bold text-5xl md:text-7xl lg:text-8xl text-white tracking-tighter mb-6 leading-tight">
            Autopilot for C/C++ Builds <br />
            <span className="text-forge-gold text-glow-gold">with Forge</span>
          </h1>

          {/* Description */}
          <p className="max-w-2xl mx-auto text-gray-400 text-lg md:text-xl mb-12 leading-relaxed">
            基于 Docker 隔离与双轨 Agent 协同的端到端编译引擎。彻底告别依赖地狱，专注代码锻造。
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/workspace">
              <Button
                size="lg"
                className="w-full sm:w-auto h-14 px-8 bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-xl border border-orange-400/50 shadow-[0_0_30px_rgba(234,88,12,0.3)] transition-all hover:scale-105 active:scale-95 group"
              >
                进入工作台 (Enter Workspace)
                <ArrowRight className="w-5 h-5 ml-2 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
            <Button
              variant="outline"
              size="lg"
              asChild
              className="w-full sm:w-auto h-14 px-8 bg-white/5 text-white border-white/10 font-bold rounded-xl transition-all hover:bg-white/10 hover:border-white/20 active:scale-95"
            >
              <a
                href="https://github.com/your-org/forge"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                View Source
              </a>
            </Button>
          </div>
        </motion.div>
      </div>

      {/* Terminal and Skills Grid */}
      <div className="max-w-6xl mx-auto px-6 mt-24">
        <div className="grid md:grid-cols-[1.5fr,1fr] gap-6">
          {/* Sandbox Terminal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2, duration: 0.8 }}
            className="bg-forge-card border border-forge-border rounded-2xl overflow-hidden shadow-2xl h-[400px] flex flex-col"
          >
            <div className="p-5 border-b border-forge-border flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="font-display font-bold text-sm text-white">Sandbox Terminal</span>
              </div>
              <Terminal className="w-5 h-5 text-cyan-400" />
            </div>

            <div className="flex-1 p-8 font-mono text-sm leading-relaxed overflow-hidden">
              <div className="flex gap-2 mb-6">
                <div className="w-3 h-3 rounded-full bg-rose-400/50" />
                <div className="w-3 h-3 rounded-full bg-amber-400/50" />
                <div className="w-3 h-3 rounded-full bg-emerald-400/50" />
              </div>

              <div className="space-y-1">
                <p className="text-gray-500 flex gap-2">
                  <span className="text-forge-gold">&gt;</span> forge init project_alpha
                </p>
                <p className="text-gray-400 ml-4 font-medium italic">Initializing neural pathways...</p>
                <p className="text-gray-400 ml-4">
                  Allocating cognitive resources... <span className="text-emerald-400">[OK]</span>
                </p>
                <p className="text-white flex gap-2">
                  <span className="text-forge-gold">&gt;</span> <span className="text-cyan-400">Ready for input</span><span className="w-2 h-5 bg-cyan-400 animate-pulse inline-block" />
                </p>
              </div>
            </div>
          </motion.div>

          {/* Cognitive Skills Card */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.8 }}
            className="bg-forge-card border border-forge-border rounded-2xl p-8 flex flex-col items-center justify-center text-center group transition-all hover:border-forge-gold/30 hover:bg-forge-gold/[0.02]"
          >
            <div className="w-20 h-20 rounded-full bg-forge-gold/5 border border-forge-gold/20 flex items-center justify-center mb-10 glow-gold group-hover:scale-110 transition-transform ring-4 ring-forge-gold/5">
              <BrainCircuit className="w-10 h-10 text-forge-gold" />
            </div>
            <h3 className="text-2xl font-display font-bold text-white mb-4">Cognitive Skills</h3>
            <p className="text-gray-400 leading-relaxed max-w-xs">
              Rapid adaptation and execution modules loading seamlessly.
            </p>
          </motion.div>
        </div>

        {/* Feature Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-6">
          <FeatureCard
            icon={<Cpu className="w-5 h-5" />}
            title="双轨 Agent 协同"
            desc="架构师 Agent 解析构建系统与依赖树，执行 Agent 负责沙盒内排错，思维链全程透明。"
            color="text-orange-500"
          />
          <FeatureCard
            icon={<Box className="w-5 h-5" />}
            title="纯净 Docker 沙盒"
            desc="任务在独立拉取的干净容器中执行，挂载持久化 CCache，杜绝环境污染。"
            color="text-blue-500"
          />
          <FeatureCard
            icon={<Network className="w-5 h-5" />}
            title="终结依赖地狱"
            desc="自动嗅探环境，处理复杂的 Git Submodules，深度集成现代 C++ 包管理器。"
            color="text-green-500"
          />
          <div className="bg-forge-card border border-forge-border rounded-2xl p-8 flex flex-col items-center justify-center gap-3 group cursor-pointer transition-all hover:border-white/20">
            <div className="w-12 h-12 rounded-full flex items-center justify-center">
              <ArrowRight className="w-8 h-8 text-gray-500 group-hover:text-white transition-all transform group-hover:translate-x-1" />
            </div>
            <span className="text-sm font-bold text-gray-500 group-hover:text-white">See all updates</span>
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
    <div className="bg-forge-card border border-forge-border rounded-2xl p-8 transition-all hover:border-white/20 hover:translate-y-[-4px]">
      <div className={cn("inline-flex p-2 rounded-lg bg-white/5 mb-6 opacity-80", color)}>
        {icon}
      </div>
      <h4 className="text-lg font-bold text-white mb-2">{title}</h4>
      <p className="text-sm text-gray-500 leading-relaxed font-medium">{desc}</p>
    </div>
  );
}
