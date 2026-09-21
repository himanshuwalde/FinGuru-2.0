import { useAuthModal } from "@/store/authModal";

export function FinalCta() {
  const openModal = useAuthModal((state) => state.openModal);

  return (
    <section className="relative overflow-hidden py-28">
      <div className="bg-grid absolute inset-0 [mask-image:radial-gradient(ellipse_50%_60%_at_50%_50%,black,transparent)]" />
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="hero-glow size-[480px] rounded-full bg-[radial-gradient(closest-side,rgba(34,197,94,0.14),transparent)]" />
      </div>

      <div className="relative z-10 mx-auto flex max-w-2xl flex-col items-center px-6 text-center">
        <h2 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          Take the command seat.
        </h2>
        <p className="mt-3 text-muted">
          Your net worth, your goals, your family's future — finally in one view.
        </p>
        <button
          type="button"
          onClick={() => openModal("login")}
          className="mt-8 rounded-xl bg-accent px-8 py-3.5 text-base font-semibold text-on-accent shadow-[0_0_40px_rgba(34,197,94,0.35)] transition-all hover:bg-accent-hover hover:shadow-[0_0_60px_rgba(34,197,94,0.45)]"
        >
          Enter FinGuru
        </button>
      </div>
    </section>
  );
}
