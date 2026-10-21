import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/cn";

type CardProps = ComponentPropsWithoutRef<"section"> & { as?: "section" | "div" | "article" | "ul" };

export function Card({ as: Tag = "section", className, ...props }: CardProps) {
  return <Tag className={cn("rounded-2xl border border-line bg-surface", className)} {...props} />;
}

/** Title bar for a card that holds a table or list. */
export function CardHeader({ title, aside, className }: { title: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 border-b border-line px-4 py-3", className)}>
      <h2 className="text-sm font-semibold">{title}</h2>
      {aside}
    </div>
  );
}
