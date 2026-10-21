import { Bot } from "lucide-react";
import { siGooglegemini, siOkta, type SimpleIcon } from "simple-icons";

// Brand marks from simple-icons (CC0 SVG data; the marks remain their owners' trademarks).
// simple-icons does not include the OpenAI logo, so OpenAI uses a neutral glyph.
const ICONS: Record<"gemini" | "okta", SimpleIcon> = { gemini: siGooglegemini, okta: siOkta };

export function BrandLogo({
  brand,
  className = "size-6",
}: {
  brand: "gemini" | "okta" | "openai";
  className?: string;
}) {
  if (brand === "openai") return <Bot className={className} aria-hidden="true" />;
  const icon = ICONS[brand];
  return (
    <svg viewBox="0 0 24 24" className={className} fill={`#${icon.hex}`} aria-hidden="true">
      <path d={icon.path} />
    </svg>
  );
}
