import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge the custom color tokens from styles/globals.css so e.g.
// `text-muted` and `text-primary` are treated as conflicting text colors.
const COLORS = ["paper", "surface", "ink", "muted", "line", "primary", "primary-ink", "primary-soft"].concat(
  ["danger", "ok", "warn"].flatMap((tone) => [tone, `${tone}-soft`]),
);

const twMerge = extendTailwindMerge({
  extend: { theme: { color: COLORS } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
