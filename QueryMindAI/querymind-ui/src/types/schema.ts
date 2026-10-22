/** querymind-api `GET /admin/schema`: tables and views documented in the schema files. */

export type SchemaColumn = {
  name: string;
  /** As declared, e.g. VARCHAR(255); null for views. */
  data_type: string | null;
  /** null when unknown (views). */
  nullable: boolean | null;
  primary_key: boolean;
  /** "table.column" this column points to. */
  references: string | null;
  description: string;
};

export type ForeignKey = { columns: string[]; references_table: string; references_columns: string[] };

export type SchemaRelation = {
  name: string;
  kind: "table" | "view";
  description: string;
  notes: string;
  columns: SchemaColumn[];
  primary_key: string[];
  foreign_keys: ForeignKey[];
  indexes: string[];
};

export type SchemaFile = {
  database: string;
  dialect: string;
  source: string;
  tables: SchemaRelation[];
};
