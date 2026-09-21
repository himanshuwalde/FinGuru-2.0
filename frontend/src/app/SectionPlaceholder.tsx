import { useParams } from "react-router-dom";

import { ALL_NAV_ITEMS } from "@/app/nav";

export function SectionPlaceholder() {
  const { section } = useParams();
  const item = ALL_NAV_ITEMS.find((navItem) => navItem.to.endsWith(`/${section}`));

  return (
    <div>
      <h1 className="text-xl font-semibold text-ink">{item?.label ?? section}</h1>
      <p className="mt-6 rounded-xl border border-dashed border-edge bg-surface p-5 text-sm text-muted">
        Planned for a later phase — the backend router and page for this module are not built yet.
      </p>
    </div>
  );
}
