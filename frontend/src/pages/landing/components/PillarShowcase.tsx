import { Bot, GraduationCap, LayoutDashboard, Shield, ShieldCheck, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface Pillar {
  icon: LucideIcon;
  title: string;
  description: string;
  preview: ReactNode;
}

const PILLARS: Pillar[] = [
  {
    icon: LayoutDashboard,
    title: "Track",
    description: "Net worth, transactions, budgets and anomalies — your whole money picture, live.",
    preview: (
      <div>
        <div className="h-1.5 overflow-hidden rounded-full bg-edge">
          <div className="h-full w-[65%] rounded-full bg-accent" />
        </div>
        <p className="numeric mt-2 text-[11px] text-muted">₹26,150 of ₹40,000 budget</p>
      </div>
    ),
  },
  {
    icon: TrendingUp,
    title: "Grow",
    description: "Portfolio health, FIRE projections, tax planning and 18+ calculators that compound.",
    preview: (
      <div>
        <svg viewBox="0 0 120 36" className="h-9 w-full" aria-hidden="true">
          <defs>
            <linearGradient id="grow-spark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22C55E" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#22C55E" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path
            d="M0 30 L20 26 L40 28 L60 19 L80 21 L100 9 L120 5 L120 36 L0 36 Z"
            fill="url(#grow-spark)"
          />
          <path
            d="M0 30 L20 26 L40 28 L60 19 L80 21 L100 9 L120 5"
            fill="none"
            stroke="#22C55E"
            strokeWidth="2"
          />
        </svg>
        <p className="numeric mt-1 text-[11px] text-muted">Portfolio XIRR +14.2%</p>
      </div>
    ),
  },
  {
    icon: GraduationCap,
    title: "Learn",
    description: "Money School lessons and quizzes that make the jargon finally click.",
    preview: (
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-md border border-edge bg-surface-hover px-2 py-1 text-[11px] text-ink">
          Lesson: XIRR
        </span>
        <span className="rounded-md bg-accent/15 px-2 py-1 text-[11px] font-medium text-accent">
          +50 XP
        </span>
      </div>
    ),
  },
  {
    icon: Shield,
    title: "Protect",
    description: "Insurance guidance, purchase guardrails and a legacy plan for generations.",
    preview: (
      <div className="flex items-center gap-2 text-[11px] text-muted">
        <ShieldCheck className="size-4 text-accent" />
        3 goals guarded · runway 14 months
      </div>
    ),
  },
  {
    icon: Bot,
    title: "AI CFO",
    description: "A grounded CFO that explains every number — because it never invents one.",
    preview: (
      <div className="space-y-1.5">
        <p className="ml-auto w-fit max-w-[90%] rounded-lg rounded-br-sm bg-surface-hover px-2 py-1 text-[11px] text-ink">
          Can I afford a ₹40k phone?
        </p>
        <p className="w-fit max-w-[90%] rounded-lg rounded-bl-sm border border-edge bg-base px-2 py-1 text-[11px] text-muted">
          Not this month — your Goa goal would slip.
        </p>
      </div>
    ),
  },
];

export function PillarShowcase() {
  return (
    <section className="relative z-10 mx-auto w-full max-w-6xl px-6 py-20">
      <div className="text-center">
        <h2 className="text-3xl font-bold tracking-tight text-ink">All five pillars. One place.</h2>
        <p className="mx-auto mt-3 max-w-xl text-muted">
          Most apps do one slice of your money life. FinGuru runs the whole building.
        </p>
      </div>

      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {PILLARS.map((pillar) => (
          <article
            key={pillar.title}
            className="flex flex-col rounded-xl border border-edge bg-surface p-5 transition-colors hover:bg-surface-hover"
          >
            <pillar.icon className="size-6 text-accent" />
            <h3 className="mt-3 text-base font-semibold text-ink">{pillar.title}</h3>
            <p className="mt-1.5 flex-1 text-sm text-muted">{pillar.description}</p>
            <div className="mt-4 rounded-lg border border-edge/60 bg-base p-3">{pillar.preview}</div>
          </article>
        ))}
      </div>
    </section>
  );
}
