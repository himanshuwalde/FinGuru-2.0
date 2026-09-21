export interface PillarMeta {
  title: string;
  blurb: string;
}

export function PillarPage({ meta }: { meta: PillarMeta }) {
  return (
    <div>
      <h1 className="text-xl font-semibold text-ink">{meta.title}</h1>
      <p className="mt-1 max-w-xl text-sm text-muted">{meta.blurb}</p>
      <p className="mt-6 rounded-xl border border-dashed border-edge bg-surface p-5 text-sm text-muted">
        This pillar is scaffolded and wired into navigation. Its modules arrive in later build
        phases.
      </p>
    </div>
  );
}
