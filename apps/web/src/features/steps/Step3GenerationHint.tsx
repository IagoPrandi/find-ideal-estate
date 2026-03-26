/** Etapa PRD 3 — geração de zonas: texto de apoio + CTA quando o mapa já tem zonas. */
export type Step3GenerationHintProps = {
  zonesReady: boolean;
  onContinueToCompare: () => void;
};

export function Step3GenerationHint({ zonesReady, onContinueToCompare }: Step3GenerationHintProps) {
  return (
    <section className="gem-panel-section animate-[fadeIn_0.4s_ease-out] text-sm">
      <div className="gem-panel-header">
        <p className="gem-eyebrow">Etapa 3</p>
        <h3 className="gem-title mt-1">Gerando zonas candidatas</h3>
        <p className="gem-subtitle mt-1">
          Acompanhe o progresso no bloco de estado acima. Quando as zonas aparecerem no mapa, avance para comparar e
          escolher uma zona consolidada.
        </p>
      </div>
      <div className="gem-panel-body space-y-4">
        <div className="rounded-2xl border border-slate-200/80 bg-slate-50 px-3 py-3 text-xs text-slate-600">
          <p className="font-semibold text-slate-800">Pipeline em execução</p>
          <p className="mt-1">1. consolidar seed de transporte</p>
          <p>2. calcular isócronas</p>
          <p>3. enriquecer verde, alagamento, segurança e POIs</p>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
          <div className={`h-2 rounded-full bg-pastel-violet-500 transition-all duration-700 ${zonesReady ? "w-full" : "w-2/3"}`} />
        </div>
        {zonesReady ? (
          <button type="button" onClick={onContinueToCompare} className="gem-primary-button w-full">
            Continuar para comparação de zonas
          </button>
        ) : (
          <p className="text-xs text-slate-500">Aguarde a conclusão para liberar a comparação da etapa 4.</p>
        )}
      </div>
    </section>
  );
}
