import type {
  ConnectionTest,
  ModelConfig,
  ModelConfigUpdate,
  OktaConfig,
  OktaConfigUpdate,
  OktaTestResult,
} from "@/api/admin";

/** Stand-in for querymind-api's admin endpoints; keeps values in this browser. */
const KEY = "querymind-mock-admin";

type Stored = {
  model: ModelConfigUpdate & { openai_api_key?: string; gemini_api_key?: string };
  okta: OktaConfigUpdate & { client_secret?: string };
};

const DEFAULTS: Stored = {
  model: {
    llm_provider: "gemini",
    openai_model: "",
    openai_reasoning_effort: null,
    gemini_model: "",
    embedding_provider: "gemini",
    embedding_model: "",
    embedding_dimensions: 768,
  },
  okta: {
    enabled: false,
    org_url: "",
    authorization_server_id: "default",
    client_id: "",
    scopes: "openid profile email groups",
    groups_claim: "groups",
    admin_group: "",
    user_group: "",
    redirect_uri: "",
    post_logout_redirect_uri: "",
  },
};

function load(): Stored {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Stored>;
    return { model: { ...DEFAULTS.model, ...saved.model }, okta: { ...DEFAULTS.okta, ...saved.okta } };
  } catch {
    return structuredClone(DEFAULTS);
  }
}

function save(stored: Stored) {
  localStorage.setItem(KEY, JSON.stringify(stored));
}

const hint = (secret?: string) => (secret ? (secret.length >= 12 ? `…${secret.slice(-4)}` : "set") : null);

function applySecret(current: string | undefined, update: string | undefined) {
  return update === undefined ? current : update || undefined;
}

export async function getModelConfig(): Promise<ModelConfig> {
  const { model } = load();
  const active =
    model.llm_provider === "openai" ? model.openai_model || "gpt-6-luna" : model.gemini_model || "gemini-3.8-flash";
  return {
    llm_provider: model.llm_provider,
    active_model: active,
    openai: {
      model: model.openai_model,
      default_model: "gpt-6-luna",
      api_key: hint(model.openai_api_key),
      reasoning_effort: model.openai_reasoning_effort,
    },
    gemini: { model: model.gemini_model, default_model: "gemini-3.8-flash", api_key: hint(model.gemini_api_key) },
    embedding: {
      provider: model.embedding_provider,
      model: model.embedding_model,
      default_models: { gemini: "gemini-embedding-001", fastembed: "BAAI/bge-small-en-v1.5" },
      dimensions: model.embedding_dimensions,
    },
    reasoning_efforts: ["none", "low", "medium", "high", "xhigh", "max"],
    config_file: "(mock) browser storage",
    warnings: ["Mock mode: settings are kept in this browser, not in the server's config file."],
  };
}

export async function saveModelConfig(update: ModelConfigUpdate): Promise<ModelConfig> {
  const stored = load();
  stored.model = {
    ...update,
    openai_api_key: applySecret(stored.model.openai_api_key, update.openai_api_key),
    gemini_api_key: applySecret(stored.model.gemini_api_key, update.gemini_api_key),
  };
  save(stored);
  return getModelConfig();
}

export async function testModelConfig(): Promise<ConnectionTest> {
  const config = await getModelConfig();
  const provider = config.llm_provider === "openai" ? config.openai : config.gemini;
  return provider.api_key
    ? { ok: true, message: `Mock mode: ${config.active_model} would be checked against the provider.` }
    : { ok: false, message: `No API key is configured for ${config.active_model}.` };
}

export async function getOktaConfig(): Promise<OktaConfig> {
  const { okta } = load();
  const { client_secret, ...rest } = okta;
  const server = okta.authorization_server_id;
  return {
    ...rest,
    issuer: okta.org_url ? (server ? `${okta.org_url}/oauth2/${server}` : okta.org_url) : null,
    client_secret: hint(client_secret),
    config_file: "(mock) browser storage",
    warnings: ["Okta sign-in is configured here but not enforced yet; QueryMind is still open without login."],
  };
}

export async function saveOktaConfig(update: OktaConfigUpdate): Promise<OktaConfig> {
  const stored = load();
  stored.okta = {
    ...update,
    org_url: update.org_url.replace(/\/+$/, ""),
    client_secret: applySecret(stored.okta.client_secret, update.client_secret),
  };
  save(stored);
  return getOktaConfig();
}

export async function testOktaConnection(orgUrl: string, serverId: string): Promise<OktaTestResult> {
  const org = orgUrl.replace(/\/+$/, "");
  if (!/^https:\/\/[^/]+\.(okta|oktapreview|okta-emea)\.com$/.test(org)) {
    return { ok: false, message: "Mock mode: enter an https://<org>.okta.com URL." };
  }
  const issuer = serverId ? `${org}/oauth2/${serverId}` : org;
  const base = serverId ? `${issuer}/v1` : `${org}/oauth2/v1`;
  return {
    ok: true,
    message: `Mock mode: the discovery document at ${issuer} would be checked.`,
    issuer,
    authorization_endpoint: `${base}/authorize`,
    token_endpoint: `${base}/token`,
    jwks_uri: `${base}/keys`,
    scopes_supported: ["openid", "profile", "email", "groups"],
  };
}
