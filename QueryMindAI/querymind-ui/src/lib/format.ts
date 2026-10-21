const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatCell(key: string, value: string | number): string {
  if (typeof value !== "number") return value;
  if (/(revenue|sales|amount|price)/.test(key)) {
    return value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: value % 1 === 0 ? 0 : 2,
    });
  }
  return value.toLocaleString("en-US");
}

export function formatWhen(at: number): string {
  const date = new Date(at);
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}, ${date.getUTCFullYear()} ${hh}:${mm} UTC`;
}
