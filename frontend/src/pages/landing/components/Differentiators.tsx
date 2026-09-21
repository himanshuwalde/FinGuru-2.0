import { Ban, Fingerprint, Lightbulb, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Callout {
  icon: LucideIcon;
  title: string;
  description: string;
}

const CALLOUTS: Callout[] = [
  {
    icon: Lightbulb,
    title: "Every number is explainable",
    description: "Each AI-cited figure traces back to the exact engine function and inputs that produced it.",
  },
  {
    icon: Users,
    title: "Protects your family across generations, not just you",
    description: "Family health scores, claim navigators and multi-generational transfer goals.",
  },
  {
    icon: Ban,
    title: "Stops a purchase before it happens",
    description: "The Financial Guardrail weighs every checkout against your active goals — before you pay.",
  },
  {
    icon: Fingerprint,
    title: "Your net worth, provable without revealing it",
    description: "Web3 vault proofs cross a threshold without ever showing the figure.",
  },
];

export function Differentiators() {
  return (
    <section className="mx-auto w-full max-w-6xl px-6 py-20">
      <div className="text-center">
        <h2 className="text-3xl font-bold tracking-tight text-ink">
          Not another expense tracker
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-muted">
          Four things you won't get from a typical finance app.
        </p>
      </div>

      <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {CALLOUTS.map((callout) => (
          <article
            key={callout.title}
            className="rounded-xl border border-edge bg-surface p-5 transition-colors hover:bg-surface-hover"
          >
            <callout.icon className="size-6 text-accent" />
            <h3 className="mt-3 text-sm font-semibold leading-snug text-ink">{callout.title}</h3>
            <p className="mt-1.5 text-sm text-muted">{callout.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
