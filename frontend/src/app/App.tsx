import { useEffect, type ReactElement } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { SectionPlaceholder } from "@/app/SectionPlaceholder";
import { AppShell } from "@/app/AppShell";
import { Logomark } from "@/components/ui/Logomark";
import { AiCfoPage } from "@/pages/ai-cfo/AiCfoPage";
import { GrowPage } from "@/pages/grow/GrowPage";
import { AuthModal } from "@/pages/landing/components/AuthModal";
import { LandingPage } from "@/pages/landing/LandingPage";
import { LearnPage } from "@/pages/learn/LearnPage";
import { ProtectPage } from "@/pages/protect/ProtectPage";
import { TrackPage } from "@/pages/track/TrackPage";
import { useAuth } from "@/store/auth";

function AppLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

function RootRoute() {
  const user = useAuth((state) => state.user);
  return user ? <Navigate to="/track" replace /> : <LandingPage />;
}

function RequireAuth({ children }: { children: ReactElement }) {
  const user = useAuth((state) => state.user);
  if (!user) return <Navigate to="/" replace />;
  return children;
}

function Splash() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base">
      <div className="flex flex-col items-center gap-3">
        <Logomark className="size-10 text-lg" />
        <p className="text-sm text-muted">Loading FinGuru…</p>
      </div>
    </div>
  );
}

export function App() {
  const init = useAuth((state) => state.init);
  const ready = useAuth((state) => state.ready);

  useEffect(() => init(), [init]);

  if (!ready) return <Splash />;

  return (
    <>
      <Routes>
        <Route path="/" element={<RootRoute />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route path="/track" element={<TrackPage />}>
            <Route path=":section" element={<SectionPlaceholder />} />
          </Route>
          <Route path="/grow" element={<GrowPage />}>
            <Route path=":section" element={<SectionPlaceholder />} />
          </Route>
          <Route path="/learn" element={<LearnPage />}>
            <Route path=":section" element={<SectionPlaceholder />} />
          </Route>
          <Route path="/protect" element={<ProtectPage />}>
            <Route path=":section" element={<SectionPlaceholder />} />
          </Route>
          <Route path="/ai-cfo" element={<AiCfoPage />}>
            <Route path=":section" element={<SectionPlaceholder />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <AuthModal />
    </>
  );
}
