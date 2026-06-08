export type GeoAi = 'chatgpt' | 'perplexity' | 'gemini' | 'claude' | 'bing_copilot' | 'outro';

export type GeoVisibilidade = 'citado' | 'nao_citado' | 'citado_sem_link';

export interface GeoVisibilityEntry {
  data: string;
  promptId: string;
  ai: GeoAi;
  visibilidade: GeoVisibilidade;
  trecho: string;
  observacoes: string;
}

export const GEO_VISIBILITY_LOG: GeoVisibilityEntry[] = [];
