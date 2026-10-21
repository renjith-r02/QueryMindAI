import { Database } from "lucide-react";
import { siApachecassandra, siMysql, siPostgresql, type SimpleIcon } from "simple-icons";
import type { DataSourceType } from "@/features/datasources/types";

// Brand marks from simple-icons (CC0 SVG data; the marks remain their owners' trademarks).
// simple-icons does not ship AWS logos, so DynamoDB uses a neutral database glyph in a
// DynamoDB-like blue; replace it with AWS's official architecture icon if you have it.
const BRAND: Partial<Record<DataSourceType, SimpleIcon>> = {
  mysql: siMysql,
  postgresql: siPostgresql,
  cassandra: siApachecassandra,
};
const DYNAMODB_BLUE = "#4053d6";

export function DataSourceLogo({ type, className = "size-7" }: { type: DataSourceType; className?: string }) {
  const icon = BRAND[type];
  if (!icon) return <Database className={className} style={{ color: DYNAMODB_BLUE }} aria-hidden="true" />;
  return (
    <svg viewBox="0 0 24 24" className={className} fill={`#${icon.hex}`} aria-hidden="true">
      <path d={icon.path} />
    </svg>
  );
}
