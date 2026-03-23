export function formatCurrencyBr(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "Preço não informado";
  }
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0
  }).format(value);
}

export function parseFiniteNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const sanitized = value.replace(/\./g, "").replace(",", ".").trim();
    const parsed = Number(sanitized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function normalizeCategory(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}
