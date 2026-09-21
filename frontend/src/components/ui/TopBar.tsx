import { useEffect, useRef, useState } from "react";
import { Bell, ChevronDown, Search } from "lucide-react";

import { useAuth } from "@/store/auth";

export function TopBar() {
  const user = useAuth((state) => state.user);
  const signOut = useAuth((state) => state.signOut);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen]);

  const initial = (user?.email?.[0] ?? "₹").toUpperCase();

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-4 border-b border-edge bg-base/80 px-6 backdrop-blur">
      <span className="flex items-center gap-2 rounded-full border border-edge bg-surface px-3 py-1 text-xs text-muted">
        <span className="size-1.5 rounded-full bg-accent" />
        Markets nominal
      </span>
      <div className="ml-auto flex items-center gap-3">
        <label className="flex items-center gap-2 rounded-lg border border-edge bg-surface px-3 py-1.5 text-muted focus-within:border-accent/50">
          <Search className="size-3.5" />
          <input
            placeholder="Search"
            className="w-40 bg-transparent text-sm text-ink outline-none placeholder:text-muted"
          />
        </label>
        <button
          type="button"
          aria-label="Notifications"
          className="relative rounded-lg border border-edge bg-surface p-2 text-muted transition-colors hover:bg-surface-hover hover:text-ink"
        >
          <Bell className="size-4" />
          <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-danger" />
        </button>
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            className="flex items-center gap-2 rounded-lg border border-edge bg-surface px-2 py-1.5 transition-colors hover:bg-surface-hover"
          >
            <span className="numeric flex size-6 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
              {initial}
            </span>
            <span className="max-w-40 truncate text-sm text-ink">{user?.email ?? "You"}</span>
            <ChevronDown className="size-3.5 text-muted" />
          </button>
          {menuOpen ? (
            <div
              role="menu"
              className="absolute right-0 top-full z-20 mt-2 w-56 rounded-lg border border-edge bg-surface p-1 shadow-xl"
            >
              <p className="truncate px-3 py-2 text-xs text-muted">{user?.email ?? "Not signed in"}</p>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  void signOut();
                }}
                className="w-full rounded-md px-3 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-hover"
              >
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
