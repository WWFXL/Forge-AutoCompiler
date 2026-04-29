"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { Terminal, Shield, Cpu, Zap, ArrowRight, BrainCircuit, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Hero({ className }: { className?: string }) {
  return (
    <section className={cn("relative pt-32 pb-20 overflow-hidden min-h-screen", className)}>
      {/* Grid backgrounds */}
      <div className="bg-grid absolute inset-0 opacity-20" />
      <div className="bg-grid-fine absolute inset-0 opacity-40" />

      <div className="max-w-7xl mx-auto px-6 relative text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-forge-gold/10 border border-forge-gold/20 text-forge-gold text-xs font-bold tracking-widest uppercase mb-8 glow-gold">
            <Sparkles className="w-3 h-3" />
            Next Generation IDE
          </div>

          {/* Heading */}
          <h1 className="font-display font-bold text-5xl md:text-7xl lg:text-8xl text-white tracking-tighter mb-6 leading-tight">
            Learn Anything <br />
            <span className="text-forge-gold text-glow-gold">with Forge</span>
          </h1>

          {/* Description */}
          <p className="max-w-2xl mx-auto text-gray-400 text-lg md:text-xl mb-12 leading-relaxed">
            An open-source SuperAgent harness that researches, codes, and creates.
            With the help of sandboxes, memories, tools, skills and subagents, it handles
            different levels of tasks that could take minutes to hours.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/workspace">
              <Button
                size="lg"
                className="w-full sm:w-auto h-14 px-8 bg-white text-black font-bold rounded-xl transition-all hover:scale-105 active:scale-95 group"
              >
                Get Started
                <ArrowRight className="w-5 h-5 ml-2 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
            <Button
              variant="outline"
              size="lg"
              className="w-full sm:w-auto h-14 px-8 bg-white/5 text-white border-white/10 font-bold rounded-xl transition-all hover:bg-white/10 hover:border-white/20 active:scale-95"
            >
              View Documentation
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
            icon={<Zap className="w-5 h-5" />}
            title="Ultra Mode"
            desc="10x faster processing for complex tasks."
            color="text-amber-400"
          />
          <FeatureCard
            icon={<Cpu className="w-5 h-5" />}
            title="Deep Memory"
            desc="Persistent context across multiple sessions."
            color="text-cyan-400"
          />
          <FeatureCard
            icon={<Shield className="w-5 h-5" />}
            title="Forge Shield"
            desc="Enterprise-grade security protocols active."
            color="text-rose-400"
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
