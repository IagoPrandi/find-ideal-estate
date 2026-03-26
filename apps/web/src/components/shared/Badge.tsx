import { AlertTriangle, CheckCircle2, Dot, Star } from "lucide-react";

type BadgeLevel = "best" | "above" | "neutral" | "below";
type BadgeType = "safety" | "green" | "flood" | "pois";

type Props = {
  type: BadgeType;
  value: BadgeLevel | string | null | undefined;
};

const LABELS: Record<BadgeType, string> = {
  safety: "Segurança",
  green: "Verde",
  flood: "Alagamento",
  pois: "Serviços"
};

const STYLES: Record<BadgeLevel, { className: string; Icon: typeof CheckCircle2 }> = {
  best: { className: "bg-emerald-100 text-emerald-700", Icon: CheckCircle2 },
  above: { className: "bg-blue-100 text-blue-700", Icon: Star },
  neutral: { className: "bg-slate-100 text-slate-600", Icon: Dot },
  below: { className: "bg-rose-100 text-rose-700", Icon: AlertTriangle }
};

function normalizeLevel(value: Props["value"]): BadgeLevel {
  if (value === "best" || value === "above" || value === "below") {
    return value;
  }
  return "neutral";
}

export function Badge({ type, value }: Props) {
  const level = normalizeLevel(value);
  const config = STYLES[level];
  const Icon = config.Icon;

  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${config.className}`}>
      <Icon className="h-3.5 w-3.5" />
      <span>{LABELS[type]}</span>
    </span>
  );
}

export type { BadgeLevel, BadgeType };