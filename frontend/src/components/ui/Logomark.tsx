import { cn } from "@/lib/cn";

export function Logomark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-sm font-bold text-accent",
        className,
      )}
    >
      ₹
    </span>
  );
}
