import { BAIRROS } from '../data/bairros';

// Média dos distritos PUBLICADOS (analisados), não da cidade inteira.
// Os scores são normalizados 0–100 sobre os 96 distritos no pipeline, mas a camada
// pública só expõe os distritos publicados — por isso o rótulo correto é
// "média dos distritos analisados", nunca "média de São Paulo".
const avg = (arr: number[]): number =>
  arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : 0;

export const MEDIA_DISTRITOS = {
  transportScore: avg(BAIRROS.map((b) => b.transportScore)),
  greenScore: avg(BAIRROS.map((b) => b.greenScore)),
  floodRiskScore: avg(BAIRROS.map((b) => b.floodRiskScore)),
  safetyScore: avg(BAIRROS.map((b) => b.safetyScore)),
  poiScore: avg(BAIRROS.map((b) => b.poiScore)),
} as const;

export const N_DISTRITOS = BAIRROS.length;
