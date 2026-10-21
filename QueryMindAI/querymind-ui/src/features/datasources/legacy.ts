import {
  DATA_SOURCE_TYPES,
  defaultConnection,
  SECTION_KEYS,
  type DataSourceInput,
  type DataSourceType,
} from "@/features/datasources/types";

/**
 * Data sources saved in this browser by earlier versions (before settings moved to the server),
 * converted to the API format so they can be imported once.
 */
export const LEGACY_KEY = "querymind-datasources";

const CAMEL_TO_SNAKE: Record<string, string> = {
  dataLocationMap: "data_location_map",
  tableOverview: "table_overview",
  entityDiagram: "entity_diagram",
  joinPaths: "join_paths",
  returnsQuestions: "returns_questions",
  businessRules: "business_rules",
  contactPoints: "contact_points",
};

type LegacySource = {
  name?: string;
  type?: string;
  enabled?: boolean;
  connection?: Record<string, string>;
  sections?: Record<string, string>;
};

export function readLegacySources(): DataSourceInput[] {
  try {
    const saved = JSON.parse(localStorage.getItem(LEGACY_KEY) ?? "null") as { state?: { sources?: LegacySource[] } };
    return (saved?.state?.sources ?? []).flatMap(convert);
  } catch {
    return [];
  }
}

export function clearLegacySources(): void {
  localStorage.removeItem(LEGACY_KEY);
}

function convert(source: LegacySource): DataSourceInput[] {
  const type = source.type as DataSourceType;
  if (!source.name?.trim() || !DATA_SOURCE_TYPES.includes(type)) return [];
  const rename = (values: Record<string, string> = {}) =>
    Object.fromEntries(Object.entries(values).map(([key, value]) => [CAMEL_TO_SNAKE[key] ?? key, value]));
  const connection = rename(source.connection);
  const allowed = defaultConnection(type, connection); // only fields the type uses
  const sections = Object.fromEntries(
    Object.entries(rename(source.sections)).filter(
      ([key, value]) => (SECTION_KEYS as readonly string[]).includes(key) && value.trim(),
    ),
  );
  return [{ name: source.name.trim(), type, enabled: source.enabled ?? true, connection: allowed, sections }];
}
