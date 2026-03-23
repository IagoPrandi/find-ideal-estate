export type MapLayerKey =
  | "routes"
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
  train: { label: "Metrô/Trem", color: "#0f766e" },
  busStops: { label: "Paradas (ônibus/estações)", color: "#f97316" },
  zones: { label: "Zonas candidatas", color: "#845ef7" },
  flood: { label: "Alagamento", color: "#7c3aed" },
  green: { label: "Área verde", color: "#16a34a" },
  pois: { label: "POIs", color: "#d97706" },
  transportCandidates: { label: "Pontos etapa 2", color: "#ea580c" },
  transportRadius: { label: "Raio de busca etapa 2", color: "#0ea5e9" }
};
