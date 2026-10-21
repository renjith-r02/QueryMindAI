import { SECTION_KEYS, sectionHeading, TYPE_INFO, type DataSourceInput } from "@/features/datasources/types";

const HEAVY = "-- " + "=".repeat(69);
const LIGHT = "-- " + "-".repeat(69);

/**
 * Render the documentation in the comment-header format of the annotated schema
 * files under querymind-agentic/sqls/, which the indexer reads (`index` command).
 * Empty sections are left out.
 */
export function buildSchemaHeader(source: DataSourceInput): string {
  const target = source.connection.database || source.connection.keyspace || source.name;
  const lines = [
    HEAVY,
    `-- ${source.name.toUpperCase()}  (${TYPE_INFO[source.type].label})   database: ${target}`,
    HEAVY,
  ];

  let first = true;
  for (const key of SECTION_KEYS) {
    const body = source.sections[key]?.trim();
    if (!body) continue;
    // The first section sits directly under the title banner, as in the schema files.
    if (!first) lines.push("--", LIGHT);
    lines.push(`-- ${sectionHeading(key, source.type)}`);
    if (!first) lines.push(LIGHT);
    lines.push(...body.split("\n").map((line) => (line.trim() ? `--   ${line.trimEnd()}` : "--")));
    first = false;
  }
  lines.push("--", HEAVY);
  return lines.join("\n");
}
