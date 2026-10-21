export type SchemaColumn = { name: string; description: string };

export type SchemaTable = {
  name: string;
  blurb: string;
  columns: SchemaColumn[];
};
