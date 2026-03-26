export type MapLayerKey =
  | "routes"
  | "metro"
  | "train"
  | "busStops"
  | "zones"
  | "flood"
  | "green"
  | "pois"
  | "transportCandidates"
  | "transportRadius";

export const MAP_LAYER_INFO: Record<MapLayerKey, { label: string; color: string }> = {
  routes: { label: "Rotas de ônibus", color: "#9775fa" },
  metro: { label: "Linhas de metrô", color: "#e11d48" },
  train: { label: "Linhas de trem", color: "#0f766e" },
  busStops: { label: "Paradas e estações", color: "#f97316" },
  zones: { label: "Zonas candidatas", color: "#845ef7" },
  flood: { label: "Alagamento", color: "#7c3aed" },
  green: { label: "Área verde", color: "#16a34a" },
  pois: { label: "POIs", color: "#d97706" },
  transportCandidates: { label: "Pontos etapa 2", color: "#ea580c" },
  transportRadius: { label: "Raio de busca etapa 2", color: "#0ea5e9" }
};
