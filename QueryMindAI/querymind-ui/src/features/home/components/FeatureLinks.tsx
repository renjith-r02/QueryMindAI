import { Link } from "react-router-dom";
import { Database, FileBarChart, LayoutDashboard, SquareTerminal, type LucideIcon } from "lucide-react";

const FEATURES: { to: string; icon: LucideIcon; title: string; body: string }[] = [
  {
    to: "/ask",
    icon: SquareTerminal,
    title: "Natural language to SQL",
    body: "Ask a question and get accurate, read-only SQL for the right dialect.",
  },
  {
    to: "/settings",
    icon: Database,
    title: "Multiple data sources",
    body: "MySQL, PostgreSQL, Cassandra and DynamoDB, documented in one place.",
  },
  {
    to: "/history",
    icon: FileBarChart,
    title: "Reports",
    body: "Every answer keeps its SQL, results table and graph view to revisit.",
  },
  {
    to: "/dashboard",
    icon: LayoutDashboard,
    title: "Dashboards",
    body: "Save the charts that matter and see them together on your dashboard.",
  },
];

export function FeatureLinks() {
  return (
    <ul className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
      {FEATURES.map(({ to, icon: Icon, title, body }) => (
        <li key={to}>
          <Link to={to} className="group flex flex-col gap-2 rounded-2xl p-2 hover:bg-surface">
            <span className="grid size-11 place-items-center rounded-full bg-primary text-primary-ink">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="font-semibold group-hover:text-primary">{title}</span>
            <span className="text-sm leading-6 text-muted">{body}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
