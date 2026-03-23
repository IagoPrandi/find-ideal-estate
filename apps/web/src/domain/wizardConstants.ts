export type ZoneInfoKey = "pois" | "transport" | "green" | "flood" | "publicSafety";

export const ZONE_INFO_LABELS: Record<ZoneInfoKey, string> = {
  pois: "POIs da zona",
  transport: "Transporte da zona",
  green: "Área verde da zona",
  flood: "Alagamento da zona",
  publicSafety: "Segurança pública"
};

export const INTEREST_CATEGORIES = [
  "Parque",
  "Academia",
  "Mercado",
  "Restaurante",
  "Farmácia",
  "Pin livre"
] as const;

export const ZONE_RADIUS_MIN_M = 300;
export const ZONE_RADIUS_MAX_M = 2500;
export const ZONE_RADIUS_STEP_M = 50;

export function clampZoneRadius(value: number): number {
  return Math.max(ZONE_RADIUS_MIN_M, Math.min(ZONE_RADIUS_MAX_M, Math.round(value)));
}
