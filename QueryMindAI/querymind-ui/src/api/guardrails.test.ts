import { afterEach, describe, expect, it, vi } from "vitest";
import type { GuardrailSettings } from "@/api/guardrails";

const settings: GuardrailSettings = {
  question_rules: [],
  blocked_sql_keywords: ["DELETE"],
  restricted_columns: [],
  max_rows: 10,
  updated_at: 5,
  required_sql_keywords: ["DELETE"],
  locked_rule_ids: [],
  polite_token: "{polite}",
};

async function withApi(response: Response) {
  vi.stubEnv("VITE_API_URL", "http://api.test");
  vi.stubEnv("VITE_USE_MOCKS", "false");
  const fetchMock = vi.fn(async () => response);
  vi.stubGlobal("fetch", fetchMock);
  vi.resetModules();
  return { api: await import("@/api/guardrails"), fetchMock };
}

const call = (fetchMock: ReturnType<typeof vi.fn>, index = 0) =>
  fetchMock.mock.calls[index] as unknown as [string, RequestInit];

describe("guardrails API", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("reads the policy from GET /guardrails", async () => {
    const { api, fetchMock } = await withApi(Response.json(settings));
    expect(await api.getGuardrails()).toEqual(settings);
    expect(call(fetchMock)[0]).toBe("http://api.test/guardrails");
  });

  it("saves only the editable fields with PUT", async () => {
    const { api, fetchMock } = await withApi(Response.json(settings));
    await api.saveGuardrails(api.toPolicy(settings));
    const [url, init] = call(fetchMock);
    expect([url, init.method]).toEqual(["http://api.test/guardrails", "PUT"]);
    expect(JSON.parse(init.body as string)).toEqual({
      question_rules: [],
      blocked_sql_keywords: ["DELETE"],
      restricted_columns: [],
      max_rows: 10,
    });
  });

  it("resets and checks with POST", async () => {
    const { api, fetchMock } = await withApi(Response.json(settings));
    await api.resetGuardrails();
    expect(call(fetchMock)).toEqual(["http://api.test/guardrails/reset", expect.objectContaining({ method: "POST" })]);

    fetchMock.mockResolvedValueOnce(Response.json({ question: null, sql: { allowed: true, reason: null } }));
    await api.checkGuardrails({ sql: "SELECT 1" });
    const [url, init] = call(fetchMock, 1);
    expect([url, JSON.parse(init.body as string)]).toEqual(["http://api.test/guardrails/check", { sql: "SELECT 1" }]);
  });

  it("surfaces the server's validation message", async () => {
    const { api } = await withApi(
      Response.json({ detail: "The rule 'delete-data' (Deleting data) cannot be disabled." }, { status: 422 }),
    );
    await expect(api.saveGuardrails(api.toPolicy(settings))).rejects.toThrow("cannot be disabled");
  });
});
