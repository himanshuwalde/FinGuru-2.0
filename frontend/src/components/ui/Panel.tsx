import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface PanelProps {
  title?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Panel({ title, actions, className, children }: PanelProps) {
  return (
    <section className={cn("rounded-xl border border-edge bg-surface p-5", className)}>
      {title || actions ? (
        <header className="mb-4 flex items-center justify-between gap-4">
          <h3 className="text-sm font-medium text-muted">{title}</h3>
          {actions}
        </header>
      ) : null}
      {children}
    </section>
  );
}
