import { cn } from "@/lib/cn";
import type { RunStatus } from "@/types/run";

const TONES: Record<RunStatus, string> = {
  blocked: "bg-danger-soft text-danger",
  healed: "bg-primary-soft text-primary",
  success: "bg-ok-soft text-ok",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={cn("w-fit rounded-full px-2 py-1 text-xs font-medium capitalize", TONES[status])}>{status}</span>
  );
}
