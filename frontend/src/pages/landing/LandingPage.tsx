import { Logomark } from "@/components/ui/Logomark";

import { Differentiators } from "./components/Differentiators";
import { FinalCta } from "./components/FinalCta";
import { Hero } from "./components/Hero";
import { PillarShowcase } from "./components/PillarShowcase";
import { TrustSection } from "./components/TrustSection";

export function LandingPage() {
  return (
    <div className="min-h-screen bg-base">
      <Hero />
      <PillarShowcase />
      <Differentiators />
      <TrustSection />
      <FinalCta />

      <footer className="border-t border-edge">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-6 py-8 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Logomark className="size-5 text-[10px]" />
            <span className="font-medium text-ink">FinGuru</span>
            <span>© 2026</span>
          </div>
          <p>
            FinGuru is a personal-finance dashboard, not a registered broker or investment advisor.
            Basket and fund content is illustrative.
          </p>
        </div>
      </footer>
    </div>
  );
}
