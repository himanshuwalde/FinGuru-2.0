const BADGES = [
  "Supabase backend",
  "Grounded Gemini AI",
  "190+ passing engine tests",
  "Made for India",
];

export function TrustSection() {
  return (
    <section className="mx-auto w-full max-w-4xl px-6 pb-20">
      <div className="rounded-xl border border-edge bg-surface px-6 py-10 text-center">
        <h2 className="text-xl font-semibold text-ink">
          Built as a final-year engineering project
        </h2>
        <p className="mx-auto mt-2 max-w-lg text-sm text-muted">
          Real architecture, not a mockup — a tested engine suite, row-level security on your data,
          and an AI that only explains what the math already computed.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {BADGES.map((badge) => (
            <span
              key={badge}
              className="rounded-full border border-edge bg-base px-3 py-1 text-xs text-muted"
            >
              {badge}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
