import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

const VARIANTS = {
  primary: "bg-primary px-5 font-semibold text-primary-ink",
  outline: "border border-line bg-surface px-3",
} as const;

type ButtonProps = ComponentPropsWithoutRef<"button"> & { variant?: keyof typeof VARIANTS };

export function Button({ variant = "outline", type = "button", className, ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl text-sm disabled:opacity-60",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}
