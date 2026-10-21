import { describe, expect, it } from "vitest";
import { clearLegacySources, LEGACY_KEY, readLegacySources } from "@/features/datasources/legacy";

function saveLegacy(sources: unknown[]) {
  localStorage.setItem(LEGACY_KEY, JSON.stringify({ state: { sources }, version: 1 }));
}

describe("legacy browser data sources", () => {
  it("converts the old browser format to the API format", () => {
    saveLegacy([
      {
        id: "old",
        name: " events ",
        type: "cassandra",
        enabled: false,
        connection: { contactPoints: "10.0.0.1", port: "9042", host: "ignored" },
        sections: { joinPaths: "By user.", businessRules: "", purpose: "Clicks." },
      },
      { name: "bad", type: "oracle" },
      { type: "mysql" },
    ]);
    expect(readLegacySources()).toEqual([
      {
        name: "events",
        type: "cassandra",
        enabled: false,
        connection: { contact_points: "10.0.0.1", port: "9042", keyspace: "", datacenter: "", username: "" },
        sections: { join_paths: "By user.", purpose: "Clicks." },
      },
    ]);
  });

  it("returns nothing for missing or corrupt data, and clears", () => {
    expect(readLegacySources()).toEqual([]);
    localStorage.setItem(LEGACY_KEY, "{not json");
    expect(readLegacySources()).toEqual([]);
    saveLegacy([{ name: "x", type: "mysql" }]);
    clearLegacySources();
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });
});
