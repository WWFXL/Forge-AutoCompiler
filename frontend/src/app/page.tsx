import { Footer } from "@/components/landing/footer";
import { Header } from "@/components/landing/header";
import { Hero } from "@/components/landing/hero";
import { SkillsSection } from "@/components/landing/sections/skills-section";
import { WhatsNewSection } from "@/components/landing/sections/whats-new-section";

export default function LandingPage() {
  return (
    <div className="min-h-screen w-full bg-forge-bg dark">
      <Header />
      <main className="flex w-full flex-col">
        <Hero />
        <SkillsSection />
        <WhatsNewSection />
      </main>
      <Footer />
    </div>
  );
}
