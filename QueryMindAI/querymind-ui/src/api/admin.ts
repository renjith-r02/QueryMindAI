import { apiFetch } from "@/api/client";
import { env } from "@/config/env";

/** Secrets are write-only: undefined keeps the saved value, "" removes it, a string replaces it. */
export type SecretUpdate = string | undefined;

export type ReasoningEffort = "none" | "low" | "medium" | "high" | "xhigh" | "max";

/** querymind-api `GET /admin/model-config`. */
export type ModelConfig = {
  llm_provider: "gemini" | "openai";
  active_model: string;
  openai: { model: string; default_model: string; api_key: string | null; reasoning_effort: ReasoningEffort | null };
  gemini: { model: string; default_model: string; api_key: string | null };
  embedding: {
    provider: "gemini" | "fastembed";
    model: string;
    default_models: Record<string, string>;
    dimensions: number | null;
  };
  reasoning_efforts: ReasoningEffort[];
  config_file: string;
  warnings: string[];
};

export type ModelConfigUpdate = {
  llm_provider: "gemini" | "openai";
  openai_model: string;
  openai_reasoning_effort: ReasoningEffort | null;
  openai_api_key?: SecretUpdate;
  gemini_model: string;
  gemini_api_key?: SecretUpdate;
  embedding_provider: "gemini" | "fastembed";
  embedding_model: string;
  embedding_dimensions: 768 | 1536 | 3072 | null;
};

export type ConnectionTest = { ok: boolean; message: string };

/** querymind-api `GET /admin/okta`. */
export type OktaConfig = {
  enabled: boolean;
  org_url: string;
  authorization_server_id: string;
  issuer: string | null;
  client_id: string;
  client_secret: string | null;
  scopes: string;
  groups_claim: string;
  admin_group: string;
  user_group: string;
  redirect_uri: string;
  post_logout_redirect_uri: string;
  config_file: string;
  warnings: string[];
};

export type OktaConfigUpdate = Omit<OktaConfig, "issuer" | "client_secret" | "config_file" | "warnings"> & {
  client_secret?: SecretUpdate;
};

export type OktaTestResult = ConnectionTest & {
  issuer?: string | null;
  authorization_endpoint?: string | null;
  token_endpoint?: string | null;
  jwks_uri?: string | null;
  scopes_supported?: string[];
};

const mocks = () => import("@/mocks/admin");
const json = (method: "PUT" | "POST", body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export async function getModelConfig(): Promise<ModelConfig> {
  if (env.useMocks) return (await mocks()).getModelConfig();
  return apiFetch<ModelConfig>("/admin/model-config");
}

export async function saveModelConfig(update: ModelConfigUpdate): Promise<ModelConfig> {
  if (env.useMocks) return (await mocks()).saveModelConfig(update);
  return apiFetch<ModelConfig>("/admin/model-config", json("PUT", update));
}

export async function testModelConfig(): Promise<ConnectionTest> {
  if (env.useMocks) return (await mocks()).testModelConfig();
  return apiFetch<ConnectionTest>("/admin/model-config/test", json("POST"));
}

export async function getOktaConfig(): Promise<OktaConfig> {
  if (env.useMocks) return (await mocks()).getOktaConfig();
  return apiFetch<OktaConfig>("/admin/okta");
}

export async function saveOktaConfig(update: OktaConfigUpdate): Promise<OktaConfig> {
  if (env.useMocks) return (await mocks()).saveOktaConfig(update);
  return apiFetch<OktaConfig>("/admin/okta", json("PUT", update));
}

export async function testOktaConnection(orgUrl: string, authorizationServerId: string): Promise<OktaTestResult> {
  if (env.useMocks) return (await mocks()).testOktaConnection(orgUrl, authorizationServerId);
  return apiFetch<OktaTestResult>(
    "/admin/okta/test",
    json("POST", { org_url: orgUrl, authorization_server_id: authorizationServerId }),
  );
}
