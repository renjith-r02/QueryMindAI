import { afterEach, describe, expect, it, vi } from "vitest";
import type { DataSource } from "@/features/datasources/types";

const source: DataSource = {
  id: "1d1a4c7e-0000-4000-8000-000000000001",
  name: "events",
  type: "cassandra",
  enabled: true,
  connection: { contact_points: "10.0.0.1" },
  sections: { purpose: "Clicks." },
  created_at: 1,
  updated_at: 2,
};

async function withApi(response: Response) {
  vi.stubEnv("VITE_API_URL", "http://api.test");
  vi.stubEnv("VITE_USE_MOCKS", "false");
  const fetchMock = vi.fn(async () => response);
  vi.stubGlobal("fetch", fetchMock);
  vi.resetModules();
  return { api: await import("@/api/datasources"), fetchMock };
}

describe("data source API", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("lists from GET /datasources", async () => {
    const { api, fetchMock } = await withApi(Response.json([source]));
    expect(await api.listDataSources()).toEqual([source]);
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/datasources", expect.anything());
  });

  it("creates and replaces with only the editable fields", async () => {
    const { api, fetchMock } = await withApi(Response.json(source, { status: 201 }));
    await api.createDataSource(source); // id and timestamps must not be sent
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      name: "events",
      type: "cassandra",
      enabled: true,
      connection: { contact_points: "10.0.0.1" },
      sections: { purpose: "Clicks." },
    });

    fetchMock.mockResolvedValueOnce(Response.json(source));
    await api.updateDataSource(source.id, source);
    const [url, put] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe(`http://api.test/datasources/${source.id}`);
    expect(put.method).toBe("PUT");
  });

  it("deletes with DELETE and accepts 204 No Content", async () => {
    const { api, fetchMock } = await withApi(new Response(null, { status: 204 }));
    await expect(api.deleteDataSource(source.id)).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      `http://api.test/datasources/${source.id}`,
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("surfaces conflicts from the server", async () => {
    const { api } = await withApi(
      Response.json({ detail: "A data source named 'events' already exists." }, { status: 409 }),
    );
    await expect(api.createDataSource(source)).rejects.toThrow("already exists");
  });
});
