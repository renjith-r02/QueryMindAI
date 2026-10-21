import { useState, type FormEvent } from "react";
import { useLoaderData } from "react-router-dom";
import { PlugZap, Save } from "lucide-react";
import {
  getOktaConfig,
  saveOktaConfig,
  testOktaConnection,
  type OktaConfig,
  type OktaConfigUpdate,
  type OktaTestResult,
} from "@/api/admin";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { SecretField } from "@/components/ui/SecretField";
import { SwitchField } from "@/components/ui/Switch";
import { TextField } from "@/components/ui/TextField";
import { BrandLogo } from "@/features/admin/components/BrandLogo";

export async function loader() {
  return { config: await getOktaConfig() };
}

function toForm(config: OktaConfig): OktaConfigUpdate {
  return {
    enabled: config.enabled,
    org_url: config.org_url,
    authorization_server_id: config.authorization_server_id,
    client_id: config.client_id,
    scopes: config.scopes,
    groups_claim: config.groups_claim,
    admin_group: config.admin_group,
    user_group: config.user_group,
    redirect_uri: config.redirect_uri,
    post_logout_redirect_uri: config.post_logout_redirect_uri,
  };
}

/** Redirect URIs to register in the Okta app, based on where this UI is served. */
function suggestedUris() {
  const origin = window.location.origin;
  return { redirect: `${origin}/login/callback`, logout: origin };
}

export function OktaPage() {
  const { config: initial } = useLoaderData<typeof loader>();
  const [config, setConfig] = useState(initial);
  const [form, setForm] = useState<OktaConfigUpdate>(() => toForm(initial));
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [status, setStatus] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [test, setTest] = useState<OktaTestResult | null>(null);
  const set = (patch: Partial<OktaConfigUpdate>) => setForm((current) => ({ ...current, ...patch }));
  const uris = suggestedUris();

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setBusy("save");
    setStatus(null);
    try {
      const saved = await saveOktaConfig(form);
      setConfig(saved);
      setForm(toForm(saved));
      setStatus({ tone: "ok", text: "Okta settings saved." });
    } catch (error) {
      setStatus({ tone: "danger", text: error instanceof Error ? error.message : "Could not save." });
    } finally {
      setBusy(null);
    }
  }

  async function onTest() {
    setBusy("test");
    setTest(null);
    try {
      setTest(await testOktaConnection(form.org_url, form.authorization_server_id));
    } catch (error) {
      setTest({ ok: false, message: error instanceof Error ? error.message : "Could not test the connection." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <BrandLogo brand="okta" className="size-7" />
            Okta
          </span>
        }
        description={
          <>
            Single sign-on for enterprise users through an Okta OIDC web app. Saved to{" "}
            <code className="font-mono text-xs">{config.config_file}</code>.
          </>
        }
      />
      {config.warnings.map((warning) => (
        <Notice key={warning} className="py-3">
          {warning}
        </Notice>
      ))}

      <form onSubmit={onSave} className="flex flex-col gap-6">
        <Card className="flex flex-col gap-4 p-4">
          <SwitchField
            label="Enable Okta sign-in"
            detail="Requires the org URL and client ID. Sign-in is not enforced yet."
            checked={form.enabled}
            onChange={(enabled) => set({ enabled })}
          />
        </Card>

        <Card className="overflow-hidden">
          <CardHeader title="Okta org and authorization server" />
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <TextField
              label="Org URL"
              type="url"
              value={form.org_url}
              placeholder="https://acme.okta.com"
              hint="Your Okta domain, without a path"
              onChange={(org_url) => set({ org_url })}
            />
            <TextField
              label="Authorization server ID"
              value={form.authorization_server_id}
              placeholder="Empty = org authorization server"
              hint={`"default", a custom server ID, or empty for the org server`}
              onChange={(authorization_server_id) => set({ authorization_server_id })}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
            <Button onClick={onTest} disabled={busy !== null || !form.org_url}>
              <PlugZap className="size-4" />
              {busy === "test" ? "Testing…" : "Test connection"}
            </Button>
            <span className="text-xs text-muted">
              Issuer:{" "}
              <code className="font-mono">
                {form.org_url
                  ? `${form.org_url.replace(/\/+$/, "")}${form.authorization_server_id ? `/oauth2/${form.authorization_server_id}` : ""}`
                  : "—"}
              </code>
            </span>
          </div>
          {test ? <TestResult result={test} /> : null}
        </Card>

        <Card className="overflow-hidden">
          <CardHeader title="Application (OIDC web app)" />
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <TextField
              label="Client ID"
              value={form.client_id}
              placeholder="0oa…"
              onChange={(client_id) => set({ client_id })}
            />
            <SecretField
              label="Client secret"
              saved={config.client_secret}
              value={form.client_secret}
              hint="Stored on the server only (OKTA_CLIENT_SECRET)"
              onChange={(client_secret) => set({ client_secret })}
            />
            <TextField
              label="Sign-in redirect URI"
              type="url"
              value={form.redirect_uri}
              placeholder={uris.redirect}
              hint={`Register this in the Okta app, e.g. ${uris.redirect}`}
              onChange={(redirect_uri) => set({ redirect_uri })}
            />
            <TextField
              label="Sign-out redirect URI"
              type="url"
              value={form.post_logout_redirect_uri}
              placeholder={uris.logout}
              onChange={(post_logout_redirect_uri) => set({ post_logout_redirect_uri })}
            />
            <TextField
              label="Scopes"
              value={form.scopes}
              hint="Space-separated; must include openid"
              onChange={(scopes) => set({ scopes })}
            />
          </div>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader title="Access by Okta group" />
          <div className="grid gap-4 p-4 sm:grid-cols-3">
            <TextField
              label="Groups claim"
              value={form.groups_claim}
              hint="Token claim that lists the user's groups"
              onChange={(groups_claim) => set({ groups_claim })}
            />
            <TextField
              label="Admin group"
              value={form.admin_group}
              placeholder="QueryMind Admins"
              hint="Members get the admin console"
              onChange={(admin_group) => set({ admin_group })}
            />
            <TextField
              label="User group"
              value={form.user_group}
              placeholder="Everyone"
              hint="Empty allows every signed-in user"
              onChange={(user_group) => set({ user_group })}
            />
          </div>
        </Card>

        {status ? (
          <Notice tone={status.tone} className="py-3" role="status">
            {status.text}
          </Notice>
        ) : null}
        <div>
          <Button type="submit" variant="primary" disabled={busy !== null}>
            <Save className="size-4" />
            {busy === "save" ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function TestResult({ result }: { result: OktaTestResult }) {
  const rows = [
    ["Issuer", result.issuer],
    ["Authorize", result.authorization_endpoint],
    ["Token", result.token_endpoint],
    ["Keys (JWKS)", result.jwks_uri],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  return (
    <div className="border-t border-line px-4 py-3" role="status">
      <Notice tone={result.ok ? "ok" : "danger"} className="py-3">
        {result.message}
      </Notice>
      {rows.length ? (
        <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[8rem_1fr]">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted">{label}</dt>
              <dd className="font-mono break-all">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
