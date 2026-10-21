import { beforeEach, describe, expect, it } from "vitest";
import { ECOMMERCE_MYSQL } from "@/features/datasources/defaults";
import { useDataSourceStore } from "@/features/datasources/store";

const store = () => useDataSourceStore.getState();
const find = (id: string) => store().sources.find((source) => source.id === id)!;

describe("useDataSourceStore", () => {
  beforeEach(() => useDataSourceStore.setState({ sources: [ECOMMERCE_MYSQL] }));

  it("starts with the documented ecommerce MySQL source", () => {
    expect(store().sources.map((s) => [s.name, s.type])).toEqual([["ecommerce", "mysql"]]);
    expect(Object.keys(ECOMMERCE_MYSQL.sections)).toHaveLength(8);
  });

  it("adds a source with the type's default connection fields", () => {
    const id = store().add("cassandra");
    expect(find(id)).toMatchObject({
      name: "Cassandra source 1",
      enabled: true,
      connection: { contactPoints: "", port: "9042", keyspace: "", datacenter: "", username: "" },
    });
  });

  it("changing type keeps shared fields and fills new defaults", () => {
    store().changeType("ecommerce", "postgresql");
    expect(find("ecommerce").connection).toEqual({
      host: "localhost",
      port: "3306",
      database: "ecommerce",
      schema: "public",
      username: "readonly",
    });
  });

  it("updates and removes", () => {
    store().update("ecommerce", { enabled: false });
    expect(find("ecommerce").enabled).toBe(false);
    store().remove("ecommerce");
    expect(store().sources).toEqual([]);
  });
});
