/**
 * Cliente SSE (EventSource) — ponto de extensão para progresso em tempo real (PRD).
 * O fluxo atual usa principalmente polling REST em `FindIdealApp`.
 */

export function createSseUrl(_path: string): string {
  const base = typeof import.meta !== "undefined" ? import.meta.env.VITE_API_BASE || "" : "";
  return `${base.replace(/\/$/, "")}${_path}`;
}
