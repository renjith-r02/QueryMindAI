import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SwitchField } from "@/components/ui/Switch";
import { useSettingsStore } from "@/features/settings/store";

export function GuardrailsPage() {
  const settings = useSettingsStore((state) => state.settings);
  const setSettings = useSettingsStore((state) => state.setSettings);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <PageHeader title="Guardrails" description="Rules checked before a question is turned into SQL." />
      <Card as="div" className="flex flex-col gap-3 p-4">
        <SwitchField
          label="Allow only read-only questions"
          detail="Reject drop, delete, update, insert, and alter."
          checked={settings.selectOnly}
          onChange={(selectOnly) => setSettings({ selectOnly })}
        />
        <SwitchField
          label="Block destructive keywords"
          detail="Same keyword list, logged as a destructive-keyword block."
          checked={settings.blockDestructive}
          onChange={(blockDestructive) => setSettings({ blockDestructive })}
        />
        <SwitchField
          label="E-commerce domain rules"
          detail="Hide credit card, password, and similar sensitive fields."
          checked={settings.domainRules}
          onChange={(domainRules) => setSettings({ domainRules })}
        />
        <SwitchField
          label="Rate limiting"
          detail="Recorded for this sample. The demo does not throttle the browser."
          checked={settings.rateLimit}
          onChange={(rateLimit) => setSettings({ rateLimit })}
        />
        <label className="flex flex-col gap-2 border-t border-line pt-3 text-sm">
          <span className="font-medium">Max rows</span>
          <input
            type="number"
            min={1}
            max={5000}
            value={settings.maxRows}
            onChange={(event) => setSettings({ maxRows: Math.max(1, Number(event.target.value) || 1) })}
            className="min-h-11 w-32 rounded-xl border border-line px-3"
          />
        </label>
      </Card>
    </div>
  );
}
