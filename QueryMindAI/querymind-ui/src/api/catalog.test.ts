import { afterEach, describe, expect, it, vi } from "vitest";

async function withApi(response: Response) {
  vi.stubEnv("VITE_API_URL", "http://api.test");
  vi.stubEnv("VITE_USE_MOCKS", "false");
  const fetchMock = vi.fn(async () => response);
  vi.stubGlobal("fetch", fetchMock);
  vi.resetModules();
  return { api: await import("@/api/catalog"), fetchMock };
}

describe("schema API", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("reads GET /admin/schema, optionally for one database", async () => {
    const files = [{ database: "ecommerce", dialect: "mysql", source: "e.sql", tables: [] }];
    const { api, fetchMock } = await withApi(Response.json(files));
    expect(await api.getSchema()).toEqual(files);
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/admin/schema", expect.anything());

    fetchMock.mockResolvedValueOnce(Response.json(files));
    await api.getSchema("returns db");
    expect(fetchMock).toHaveBeenLastCalledWith("http://api.test/admin/schema?database=returns%20db", expect.anything());
  });
});
