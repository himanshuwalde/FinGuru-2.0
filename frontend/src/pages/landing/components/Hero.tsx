import { Logomark } from "@/components/ui/Logomark";
import { useAuthModal } from "@/store/authModal";

export function Hero() {
  const openModal = useAuthModal((state) => state.openModal);

  return (
    <section className="relative flex min-h-screen flex-col overflow-hidden">
      <div className="bg-grid absolute inset-0 [mask-image:radial-gradient(ellipse_60%_50%_at_50%_40%,black,transparent)]" />
      <div className="absolute left-1/2 top-1/3 -translate-x-1/2 -translate-y-1/2">
        <div className="hero-glow size-[560px] rounded-full bg-[radial-gradient(closest-side,rgba(34,197,94,0.16),transparent)]" />
      </div>

      <nav className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <a href="/" className="flex items-center gap-2.5">
          <Logomark className="size-8" />
          <span className="text-lg font-semibold tracking-tight text-ink">FinGuru</span>
        </a>
        <button
          type="button"
          onClick={() => openModal("login")}
          className="rounded-lg border border-edge bg-surface px-4 py-2 text-sm text-ink transition-colors hover:bg-surface-hover"
        >
          Sign in
        </button>
      </nav>

      <div className="relative z-10 mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-6 pb-28 text-center">
        <span className="rounded-full border border-edge bg-surface px-3 py-1 text-xs text-muted">
          Personal finance, engineered for India
        </span>
        <h1 className="mt-6 text-4xl font-bold tracking-tight text-ink sm:text-6xl">
          Your financial{" "}
          <span className="bg-gradient-to-r from-accent to-info bg-clip-text text-transparent">
            command center
          </span>
        </h1>
        <p className="mt-5 max-w-xl text-lg text-muted">
          Track, grow, learn and protect your money — guided by an AI CFO that never invents a
          number.
        </p>
        <button
          type="button"
          onClick={() => openModal("login")}
          className="mt-9 rounded-xl bg-accent px-8 py-3.5 text-base font-semibold text-on-accent shadow-[0_0_40px_rgba(34,197,94,0.35)] transition-all hover:bg-accent-hover hover:shadow-[0_0_60px_rgba(34,197,94,0.45)]"
        >
          Enter FinGuru
        </button>
        <p className="mt-4 text-xs text-muted">Free during beta · Your data stays yours</p>
      </div>
    </section>
  );
}
