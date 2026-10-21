export const DATA_SOURCE_TYPES = ["mysql", "postgresql", "cassandra", "dynamodb"] as const;
export type DataSourceType = (typeof DATA_SOURCE_TYPES)[number];

export type ConnectionField = { key: string; label: string; placeholder?: string; defaultValue?: string };

type TypeInfo = {
  label: string;
  /** Heading of the access-path section; joins only exist in the relational stores. */
  accessPathsHeading: string;
  connection: ConnectionField[];
};

export const TYPE_INFO: Record<DataSourceType, TypeInfo> = {
  mysql: {
    label: "MySQL",
    accessPathsHeading: "STANDARD JOIN PATHS (MySQL)",
    connection: [
      { key: "host", label: "Host", placeholder: "localhost" },
      { key: "port", label: "Port", defaultValue: "3306" },
      { key: "database", label: "Database", placeholder: "ecommerce" },
      { key: "username", label: "Username", placeholder: "readonly" },
    ],
  },
  postgresql: {
    label: "PostgreSQL",
    accessPathsHeading: "STANDARD JOIN PATHS (PostgreSQL)",
    connection: [
      { key: "host", label: "Host", placeholder: "localhost" },
      { key: "port", label: "Port", defaultValue: "5432" },
      { key: "database", label: "Database", placeholder: "returns_db" },
      { key: "schema", label: "Schema", defaultValue: "public" },
      { key: "username", label: "Username", placeholder: "readonly" },
    ],
  },
  cassandra: {
    label: "Cassandra",
    accessPathsHeading: "STANDARD QUERY PATTERNS (CQL)",
    connection: [
      { key: "contact_points", label: "Contact points", placeholder: "10.0.0.1, 10.0.0.2" },
      { key: "port", label: "Port", defaultValue: "9042" },
      { key: "keyspace", label: "Keyspace", placeholder: "shop" },
      { key: "datacenter", label: "Local datacenter", placeholder: "dc1" },
      { key: "username", label: "Username", placeholder: "readonly" },
    ],
  },
  dynamodb: {
    label: "DynamoDB",
    accessPathsHeading: "STANDARD ACCESS PATTERNS (DynamoDB)",
    connection: [
      { key: "region", label: "Region", defaultValue: "us-east-1" },
      { key: "tables", label: "Tables", placeholder: "Orders, OrderLines" },
      { key: "endpoint", label: "Endpoint URL (optional)", placeholder: "http://localhost:8000 for DynamoDB Local" },
    ],
  },
};

export const SECTION_KEYS = [
  "purpose",
  "data_location_map",
  "table_overview",
  "relationships",
  "entity_diagram",
  "join_paths",
  "returns_questions",
  "business_rules",
] as const;
export type SectionKey = (typeof SECTION_KEYS)[number];

/** Documentation sections, in the order and wording of the annotated schema files under sqls/. */
export const SECTIONS: Record<SectionKey, { heading: string; hint: string }> = {
  purpose: {
    heading: "PURPOSE",
    hint: "What the data source holds, what is NOT in it, and the query dialect to use.",
  },
  data_location_map: {
    heading: "DATA LOCATION MAP",
    hint: "Which tables live in this source and which live in other sources.",
  },
  table_overview: { heading: "TABLE OVERVIEW", hint: "One line per table: what one row means." },
  relationships: {
    heading: "RELATIONSHIPS",
    hint: "Parent 1 --- N child links, including logical links to other sources.",
  },
  entity_diagram: { heading: "ENTITY DIAGRAM (text)", hint: "A text diagram, e.g. users --< orders --< order_lines." },
  join_paths: { heading: "STANDARD JOIN PATHS", hint: "The usual way to join or look up related data." },
  returns_questions: {
    heading: "QUESTIONS THAT INVOLVE RETURNS",
    hint: "How to answer questions that need returns data, which lives in another source.",
  },
  business_rules: {
    heading: "BUSINESS RULES AND QUERY GUIDANCE",
    hint: "Numbered rules: revenue definitions, statuses that count, dates, currency.",
  },
};

export function sectionHeading(key: SectionKey, type: DataSourceType): string {
  return key === "join_paths" ? TYPE_INFO[type].accessPathsHeading : SECTIONS[key].heading;
}

/** A data source as stored by querymind-api (`GET /datasources`). */
export type DataSource = {
  id: string;
  name: string;
  type: DataSourceType;
  enabled: boolean;
  connection: Record<string, string>;
  sections: Partial<Record<SectionKey, string>>;
  created_at: number;
  updated_at: number;
  /** "env": configured only in the server's .env (QUERYMIND_DB_<NAME>); not saved in settings yet. */
  origin?: "qdrant" | "env";
};

/** What a client sends to create or replace a data source. */
export type DataSourceInput = Omit<DataSource, "id" | "created_at" | "updated_at" | "origin">;

export function toInput({ name, type, enabled, connection, sections }: DataSourceInput): DataSourceInput {
  return { name, type, enabled, connection, sections };
}

/** Connection values for `type`, keeping any that exist in `current` and filling defaults. */
export function defaultConnection(type: DataSourceType, current: Record<string, string> = {}): Record<string, string> {
  return Object.fromEntries(
    TYPE_INFO[type].connection.map((field) => [field.key, current[field.key] ?? field.defaultValue ?? ""]),
  );
}
