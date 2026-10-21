import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/cn";

const TONES = {
  neutral: "border-line bg-surface",
  danger: "border-danger/40 bg-danger-soft",
  ok: "border-ok/30 bg-ok-soft text-ok",
} as const;

/** A coloured callout box for status messages. */
export function Notice({
  tone = "neutral",
  className,
  ...props
}: ComponentPropsWithoutRef<"section"> & { tone?: keyof typeof TONES }) {
  return <section className={cn("rounded-2xl border px-4 py-4 text-sm", TONES[tone], className)} {...props} />;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-line bg-surface px-4 py-8 text-center text-sm text-muted">
      {children}
    </p>
  );
}
