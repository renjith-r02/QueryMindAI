import { Link } from "react-router-dom";
import { MoreHorizontal } from "lucide-react";
import { Composer } from "@/features/ask/components/Composer";
import { DataSourceLogo } from "@/features/datasources/components/DataSourceLogo";
import { DATA_SOURCE_TYPES, TYPE_INFO, type DataSourceType } from "@/features/datasources/types";

const TILE = "grid place-items-center rounded-2xl border border-line bg-surface shadow-sm";

/** Heading, the question box, and the data sources QueryMind connects to. */
export function HomeHero() {
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-primary-soft/70 to-paper px-4 pt-10 pb-8 sm:px-8">
      <div className="mx-auto max-w-3xl text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
          Turn questions into <span className="text-primary">SQL</span>
        </h1>
        <p className="mt-4 text-lg font-medium sm:text-2xl">Query all your data sources in natural language</p>
        <p className="mx-auto mt-3 max-w-2xl text-base leading-7 text-muted">
          A SQL app that connects to multiple data sources across different SQL dialects, and answers with AI-generated,
          read-only SQL.
        </p>
      </div>

      <div className="mx-auto mt-8 grid max-w-5xl items-center gap-4 xl:grid-cols-[7rem_1fr_7rem]">
        <SideSources types={["postgresql", "cassandra"]} side="left" />
        <Composer variant="hero" />
        <SideSources types={["mysql", "dynamodb"]} side="right" />
      </div>

      <ul className="mt-6 flex flex-wrap justify-center gap-3" aria-label="Supported data sources">
        {DATA_SOURCE_TYPES.map((type) => (
          <li key={type}>
            <Link to="/settings" className="flex w-24 flex-col items-center gap-2 text-xs text-muted hover:text-ink">
              <span className={`${TILE} size-16 hover:border-primary`}>
                <DataSourceLogo type={type} className="size-8" />
              </span>
              {TYPE_INFO[type].label}
            </Link>
          </li>
        ))}
        <li>
          <Link to="/settings" className="flex w-24 flex-col items-center gap-2 text-xs text-muted hover:text-ink">
            <span className={`${TILE} size-16 text-primary hover:border-primary`}>
              <MoreHorizontal className="size-6" aria-hidden="true" />
            </span>
            Manage
          </Link>
        </li>
      </ul>
      <p className="mt-4 text-center text-sm text-muted">
        Connect once. <span className="font-semibold text-ink">Query everything.</span>
      </p>
    </section>
  );
}

/** Decorative logos linked to the question box with curved connectors (wide screens only). */
function SideSources({ types, side }: { types: DataSourceType[]; side: "left" | "right" }) {
  const flip = side === "right" ? "-scale-x-100" : "";
  return (
    <div className="relative hidden h-56 xl:block" aria-hidden="true">
      <svg viewBox="0 0 112 224" className={`absolute inset-0 size-full ${flip}`} fill="none">
        <path d="M48 44 C 80 44, 80 112, 112 112" className="stroke-primary/30" strokeWidth="1.5" />
        <path d="M48 180 C 80 180, 80 112, 112 112" className="stroke-primary/30" strokeWidth="1.5" />
        <circle cx="48" cy="44" r="3" className="fill-primary/50" />
        <circle cx="48" cy="180" r="3" className="fill-primary/50" />
        <circle cx="110" cy="112" r="3" className="fill-primary/50" />
      </svg>
      {types.map((type, index) => (
        <span
          key={type}
          className={`${TILE} absolute size-16 ${side === "left" ? "left-0" : "right-0"} ${index === 0 ? "top-3" : "bottom-3"}`}
        >
          <DataSourceLogo type={type} className="size-8" />
        </span>
      ))}
    </div>
  );
}
