import { useState, type FormEvent, type ReactNode } from "react";
import { useLoaderData } from "react-router-dom";
import { PlugZap, Save } from "lucide-react";
import {
  getModelConfig,
  saveModelConfig,
  testModelConfig,
  type ConnectionTest,
  type ModelConfig,
  type ModelConfigUpdate,
  type ReasoningEffort,
} from "@/api/admin";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { SecretField } from "@/components/ui/SecretField";
import { SelectField } from "@/components/ui/SelectField";
import { SwitchField } from "@/components/ui/Switch";
import { TextField } from "@/components/ui/TextField";
import { BrandLogo } from "@/features/admin/components/BrandLogo";
import { useSettingsStore } from "@/features/settings/store";
import { cn } from "@/lib/cn";
import { DIALECTS } from "@/types/settings";

// Suggestions only; any model name the provider accepts can be typed.
const MODEL_SUGGESTIONS = { openai: ["gpt-6-luna", "gpt-6-sol"], gemini: ["gemini-3.8-flash", "gemini-2.5-flash"] };
const DIMENSIONS = ["768", "1536", "3072"] as const;
const PROVIDERS = [
  { id: "gemini", name: "Google Gemini", key: "GEMINI_API_KEY" },
  { id: "openai", name: "OpenAI", key: "OPENAI_API_KEY" },
] as const;

export async function loader() {
  return { config: await getModelConfig() };
}

type Form = ModelConfigUpdate;

function toForm(config: ModelConfig): Form {
  return {
    llm_provider: config.llm_provider,
    openai_model: config.openai.model,
    openai_reasoning_effort: config.openai.reasoning_effort,
    gemini_model: config.gemini.model,
    embedding_provider: config.embedding.provider,
    embedding_model: config.embedding.model,
    embedding_dimensions: (config.embedding.dimensions as Form["embedding_dimensions"]) ?? null,
  };
}

export function ModelPage() {
  const { config: initial } = useLoaderData<typeof loader>();
  const [config, setConfig] = useState(initial);
  const [form, setForm] = useState<Form>(() => toForm(initial));
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [status, setStatus] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const set = (patch: Partial<Form>) => setForm((current) => ({ ...current, ...patch }));

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setBusy("save");
    setStatus(null);
    try {
      const saved = await saveModelConfig(form);
      setConfig(saved);
      setForm(toForm(saved));
      setStatus({ tone: "ok", text: `Saved. New questions use ${saved.active_model}.` });
    } catch (error) {
      setStatus({ tone: "danger", text: error instanceof Error ? error.message : "Could not save." });
    } finally {
      setBusy(null);
    }
  }

  async function onTest() {
    setBusy("test");
    setStatus(null);
    try {
      const result: ConnectionTest = await testModelConfig();
      setStatus({ tone: result.ok ? "ok" : "danger", text: result.message });
    } catch (error) {
      setStatus({ tone: "danger", text: error instanceof Error ? error.message : "Could not test the connection." });
    } finally {
      setBusy(null);
    }
  }

  const embeddingDefault = config.embedding.default_models[form.embedding_provider] ?? "";

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Model config"
        description={
          <>
            The language model that writes SQL and answers, and the embedding model used for search. Saved to{" "}
            <code className="font-mono text-xs">{config.config_file}</code> and used for new questions right away.
          </>
        }
      />
      {config.warnings.map((warning) => (
        <Notice key={warning} className="py-3">
          {warning}
        </Notice>
      ))}

      <form onSubmit={onSave} className="flex flex-col gap-6">
        <Card className="overflow-hidden">
          <CardHeader
            title="Language model"
            aside={
              <span className="text-xs text-muted">
                In use: <span className="font-mono">{config.active_model}</span>
              </span>
            }
          />
          <div className="flex flex-col gap-5 p-4">
            <fieldset>
              <legend className="mb-2 text-sm font-medium">Provider for SQL and answers</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {PROVIDERS.map((provider) => (
                  <label
                    key={provider.id}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-2xl border border-line p-4 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary",
                      form.llm_provider === provider.id && "border-primary bg-primary-soft/50",
                    )}
                  >
                    <input
                      type="radio"
                      name="llm_provider"
                      value={provider.id}
                      checked={form.llm_provider === provider.id}
                      onChange={() => set({ llm_provider: provider.id })}
                      className="sr-only"
                    />
                    <BrandLogo brand={provider.id} className="size-7" />
                    <span className="flex-1 font-medium">{provider.name}</span>
                    {form.llm_provider === provider.id ? (
                      <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-ink">
                        Selected
                      </span>
                    ) : null}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-4 lg:grid-cols-2">
              <ProviderCard brand="gemini" title="Google Gemini" active={form.llm_provider === "gemini"}>
                <TextField
                  label="Model"
                  value={form.gemini_model}
                  placeholder={config.gemini.default_model}
                  list="gemini-models"
                  hint={`GEMINI_MODEL. Empty uses ${config.gemini.default_model}.`}
                  onChange={(gemini_model) => set({ gemini_model })}
                />
                <datalist id="gemini-models">
                  {MODEL_SUGGESTIONS.gemini.map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
                <SecretField
                  label="API key"
                  saved={config.gemini.api_key}
                  value={form.gemini_api_key}
                  hint="GEMINI_API_KEY. Also used for Gemini embeddings."
                  onChange={(gemini_api_key) => set({ gemini_api_key })}
                />
              </ProviderCard>

              <ProviderCard brand="openai" title="OpenAI" active={form.llm_provider === "openai"}>
                <TextField
                  label="Model"
                  value={form.openai_model}
                  placeholder={config.openai.default_model}
                  list="openai-models"
                  hint={`OPENAI_MODEL. Empty uses ${config.openai.default_model}.`}
                  onChange={(openai_model) => set({ openai_model })}
                />
                <datalist id="openai-models">
                  {MODEL_SUGGESTIONS.openai.map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
                <SecretField
                  label="API key"
                  saved={config.openai.api_key}
                  value={form.openai_api_key}
                  hint="OPENAI_API_KEY"
                  onChange={(openai_api_key) => set({ openai_api_key })}
                />
                <SelectField
                  label="Reasoning effort"
                  value={form.openai_reasoning_effort ?? "Model default"}
                  options={["Model default", ...config.reasoning_efforts]}
                  onChange={(value) =>
                    set({ openai_reasoning_effort: value === "Model default" ? null : (value as ReasoningEffort) })
                  }
                />
              </ProviderCard>
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader
            title="Embeddings"
            aside={<span className="text-xs text-muted">Used to search the knowledge base</span>}
          />
          <div className="grid gap-4 p-4 sm:grid-cols-3">
            <SelectField
              label="Provider"
              value={form.embedding_provider === "gemini" ? "Google Gemini" : "FastEmbed (local, no key)"}
              options={["Google Gemini", "FastEmbed (local, no key)"]}
              onChange={(label) => set({ embedding_provider: label === "Google Gemini" ? "gemini" : "fastembed" })}
            />
            <TextField
              label="Model"
              value={form.embedding_model}
              placeholder={embeddingDefault}
              hint={`EMBEDDING_MODEL. Empty uses ${embeddingDefault}.`}
              onChange={(embedding_model) => set({ embedding_model })}
            />
            {form.embedding_provider === "gemini" ? (
              <SelectField
                label="Dimensions"
                value={String(form.embedding_dimensions ?? 768) as (typeof DIMENSIONS)[number]}
                options={DIMENSIONS}
                onChange={(value) => set({ embedding_dimensions: Number(value) as Form["embedding_dimensions"] })}
              />
            ) : null}
          </div>
          <p className="border-t border-line px-4 py-3 text-xs text-muted">
            Changing the embedding provider, model or dimensions requires re-indexing the knowledge base (POST /index
            with recreate=true).
          </p>
        </Card>

        {status ? (
          <Notice tone={status.tone} className="py-3" role="status">
            {status.text}
          </Notice>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" disabled={busy !== null}>
            <Save className="size-4" />
            {busy === "save" ? "Saving…" : "Save"}
          </Button>
          <Button onClick={onTest} disabled={busy !== null} title="Checks the saved key and model; uses no tokens">
            <PlugZap className="size-4" />
            {busy === "test" ? "Testing…" : "Test saved connection"}
          </Button>
        </div>
      </form>

      <DisplaySettings />
    </div>
  );
}

function ProviderCard({
  brand,
  title,
  active,
  children,
}: {
  brand: "gemini" | "openai";
  title: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={`${title} settings`}
      className={cn("flex flex-col gap-4 rounded-2xl border border-line p-4", !active && "bg-paper/60")}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <BrandLogo brand={brand} className="size-5" />
        {title}
        {active ? null : <span className="text-xs font-normal text-muted">(not selected)</span>}
      </h3>
      {children}
    </section>
  );
}

/** SQL display preferences; these stay in this browser. */
function DisplaySettings() {
  const settings = useSettingsStore((state) => state.settings);
  const setSettings = useSettingsStore((state) => state.setSettings);
  return (
    <Card className="overflow-hidden">
      <CardHeader title="SQL display" aside={<span className="text-xs text-muted">Saved in this browser</span>} />
      <div className="flex flex-col gap-4 p-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Primary dialect"
            value={settings.primaryDialect}
            options={DIALECTS}
            onChange={(primaryDialect) => setSettings({ primaryDialect })}
          />
          <SelectField
            label="Secondary dialect"
            value={settings.secondaryDialect}
            options={DIALECTS}
            onChange={(secondaryDialect) => setSettings({ secondaryDialect })}
          />
        </div>
        <SwitchField
          label="Multi-dialect output"
          detail="Show both statements on sample results."
          checked={settings.multiDialect}
          onChange={(multiDialect) => setSettings({ multiDialect })}
        />
        <SwitchField
          label="Explanation mode"
          detail="Plain-English breakdown next to the SQL."
          checked={settings.explanation}
          onChange={(explanation) => setSettings({ explanation })}
        />
      </div>
    </Card>
  );
}
