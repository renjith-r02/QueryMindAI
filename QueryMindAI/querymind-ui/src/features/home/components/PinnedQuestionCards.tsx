import { ArrowRight, BarChart3, PieChart, Table2, TrendingUp, X, type LucideIcon } from "lucide-react";
import { useAskNavigation } from "@/features/ask/hooks/useAskNavigation";
import { usePinnedStore } from "@/features/pinned/store";
import { SERIES_COLORS } from "@/features/results/lib/chartPalette";
import { cn } from "@/lib/cn";

type Look = { icon: LucideIcon; card: string; badge: string; preview: () => React.ReactElement };

// Card styles cycle in this order. The previews are decoration only (no real data).
const LOOKS: Look[] = [
  { icon: BarChart3, card: "bg-primary-soft/60", badge: "bg-primary-soft text-primary", preview: BarsPreview },
  { icon: PieChart, card: "bg-ok-soft/70", badge: "bg-ok-soft text-ok", preview: RankedPreview },
  { icon: TrendingUp, card: "bg-warn-soft/70", badge: "bg-warn-soft text-warn", preview: LinesPreview },
  { icon: Table2, card: "bg-danger-soft/60", badge: "bg-danger-soft text-danger", preview: TablePreview },
];

export function PinnedQuestionCards({ pinned }: { pinned: string[] }) {
  const { ask } = useAskNavigation();
  const unpin = usePinnedStore((state) => state.unpin);

  if (pinned.length === 0) {
    return <p className="mt-3 text-sm text-muted">Nothing pinned. Use the pin on a recent query to keep it here.</p>;
  }
  return (
    <ul className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {pinned.map((question, index) => {
        const look = LOOKS[index % LOOKS.length]!;
        const Icon = look.icon;
        const Preview = look.preview;
        return (
          <li key={question} className={cn("relative rounded-2xl border border-line p-3", look.card)}>
            <button
              type="button"
              onClick={() => ask(question)}
              className="group flex w-full flex-col gap-3 rounded-xl text-left"
            >
              <span className="flex items-center gap-3 pr-8">
                <span className={cn("grid size-10 shrink-0 place-items-center rounded-full", look.badge)}>
                  <Icon className="size-5" aria-hidden="true" />
                </span>
                <span className="flex-1 text-sm font-medium">{question}</span>
                <ArrowRight className="size-4 shrink-0 text-muted group-hover:text-primary" aria-hidden="true" />
              </span>
              <span className="block h-24 rounded-xl border border-line bg-surface p-3" aria-hidden="true">
                <Preview />
              </span>
            </button>
            <button
              type="button"
              aria-label={`Unpin "${question}"`}
              title="Unpin"
              onClick={() => unpin(question, pinned)}
              className="absolute top-1 right-1 inline-flex size-8 items-center justify-center rounded-lg text-muted hover:bg-surface hover:text-ink"
            >
              <X className="size-4" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

const MUTED = "#e3e8ef";

function BarsPreview() {
  const heights = [30, 42, 55, 80, 62, 74, 90];
  return (
    <svg viewBox="0 0 140 60" className="size-full" preserveAspectRatio="none">
      {heights.map((h, i) => (
        <rect
          key={i}
          x={4 + i * 19}
          y={60 - h * 0.6}
          width="12"
          height={h * 0.6}
          rx="2"
          fill={SERIES_COLORS[0]}
          opacity={0.35 + i * 0.09}
        />
      ))}
    </svg>
  );
}

function RankedPreview() {
  const widths = [64, 52, 38, 30, 20];
  return (
    <svg viewBox="0 0 140 60" className="size-full" preserveAspectRatio="none">
      {widths.map((w, i) => (
        <g key={i}>
          <rect x="2" y={4 + i * 11} width="30" height="5" rx="2" fill={MUTED} />
          <rect x="40" y={4 + i * 11} width="18" height="5" rx="2" fill={MUTED} />
          <rect x="66" y={4 + i * 11} width={w} height="5" rx="2" fill={SERIES_COLORS[2]} />
        </g>
      ))}
    </svg>
  );
}

function LinesPreview() {
  const series = [
    "2,40 22,30 42,34 62,22 82,26 102,14 122,18 138,6",
    "2,48 22,42 42,44 62,36 82,40 102,32 122,36 138,26",
    "2,54 22,52 42,50 62,48 82,50 102,46 122,44 138,42",
  ];
  return (
    <svg viewBox="0 0 140 60" className="size-full" preserveAspectRatio="none">
      {series.map((points, i) => (
        <polyline
          key={i}
          points={points}
          fill="none"
          stroke={SERIES_COLORS[i]}
          strokeWidth="2"
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}

function TablePreview() {
  return (
    <svg viewBox="0 0 140 60" className="size-full" preserveAspectRatio="none">
      <rect x="0" y="0" width="140" height="10" rx="2" fill={MUTED} />
      <rect x="56" y="3" width="28" height="4" rx="2" fill={SERIES_COLORS[0]} />
      {[0, 1, 2, 3].map((row) => (
        <g key={row}>
          <rect x="4" y={16 + row * 11} width="38" height="5" rx="2" fill={MUTED} />
          <rect x="56" y={16 + row * 11} width="28" height="5" rx="2" fill={MUTED} />
          <rect x="98" y={16 + row * 11} width="30" height="5" rx="2" fill={MUTED} />
        </g>
      ))}
    </svg>
  );
}
