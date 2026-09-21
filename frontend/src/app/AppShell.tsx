import type { ReactNode } from "react";

import { Logomark } from "@/components/ui/Logomark";
import { SidebarNav } from "@/components/ui/SidebarNav";
import { TopBar } from "@/components/ui/TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-base">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 overflow-y-auto border-r border-edge bg-surface p-4 md:block">
        <div className="flex items-center gap-2 px-3 py-2">
          <Logomark className="size-7" />
          <div>
            <p className="text-sm font-semibold leading-none text-ink">FinGuru</p>
            <p className="mt-1 text-[10px] uppercase tracking-wider text-muted">
              Command center
            </p>
          </div>
        </div>
        <SidebarNav />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
