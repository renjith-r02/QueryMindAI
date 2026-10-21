import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { tokenizeSql } from "@/features/results/lib/sqlHighlight";

export function SqlPanel({ title, sql, note }: { title: string; sql: string; note?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1200);
    return () => window.clearTimeout(timer);
  }, [copied]);

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {note ? <p className="text-xs text-muted">{note}</p> : null}
        </div>
        <Button onClick={() => void navigator.clipboard?.writeText(sql).then(() => setCopied(true))}>
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-sm leading-6">
        {tokenizeSql(sql).map((token, index) => (
          <span key={index} className={token.keyword ? "text-primary" : undefined}>
            {token.text}
          </span>
        ))}
      </pre>
    </Card>
  );
}
