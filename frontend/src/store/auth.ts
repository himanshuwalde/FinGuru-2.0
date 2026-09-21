import { create } from "zustand";

import { supabase } from "@/lib/supabase";

export interface AuthUser {
  id: string;
  email: string | null;
}

interface AuthState {
  user: AuthUser | null;
  ready: boolean;
  recoveryPending: boolean;
  init: () => () => void;
  clearRecovery: () => void;
  signOut: () => Promise<void>;
}

function toUser(session: { user: { id: string; email?: string | null } } | null): AuthUser | null {
  if (!session?.user) return null;
  return { id: session.user.id, email: session.user.email ?? null };
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  ready: false,
  recoveryPending: false,
  init: () => {
    if (!supabase) {
      set({ ready: true });
      return () => {};
    }
    supabase.auth
      .getSession()
      .then(({ data }) => set({ user: toUser(data.session), ready: true }))
      .catch(() => set({ ready: true }));
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY") set({ recoveryPending: true });
      set({ user: toUser(session) });
    });
    return () => data.subscription.unsubscribe();
  },
  clearRecovery: () => set({ recoveryPending: false }),
  signOut: async () => {
    await supabase?.auth.signOut();
  },
}));
