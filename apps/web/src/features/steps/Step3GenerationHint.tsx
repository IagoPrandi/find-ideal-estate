/** Etapa PRD 3 — geração de zonas: texto de apoio + CTA quando o mapa já tem zonas. */
export type Step3GenerationHintProps = {
  zonesReady: boolean;
  onContinueToCompare: () => void;
};

export function Step3GenerationHint({ zonesReady, onContinueToCompare }: Step3GenerationHintProps) {
  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Geração de zonas</h3>
      <p className="mt-2 text-xs text-slate-500">
        Acompanhe o progresso no bloco de estado acima. Quando as zonas aparecerem no mapa, avance para comparar e
        escolher uma zona consolidada.
      </p>
      {zonesReady ? (
        <button
          type="button"
          onClick={onContinueToCompare}
          className="mt-4 w-full rounded-xl border border-slate-200 bg-pastel-violet-500 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-pastel-violet-600"
        >
          Continuar para comparação de zonas
        </button>
      ) : null}
    </section>
  );
}
