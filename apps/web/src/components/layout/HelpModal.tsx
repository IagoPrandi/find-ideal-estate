import { useEffect } from "react";

export type HelpModalProps = {
  open: boolean;
  onClose: () => void;
};

export function HelpModal({ open, onClose }: HelpModalProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-slate-900/50 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="help-modal-title"
    >
      <div className="w-full max-w-lg rounded-[28px] border border-white/70 bg-white/95 p-6 shadow-2xl">
        <p className="gem-eyebrow">Ajuda rápida</p>
        <h2 id="help-modal-title" className="mt-1 text-xl font-extrabold tracking-tight text-slate-900">
          Fluxo guiado pelo PRD
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-500">
          Defina um ponto de referência no mapa, configure tempo e raio, encontre transportes elegíveis e siga a jornada até a
          comparação final de imóveis e dashboard da zona.
        </p>
        <div className="mt-4 space-y-3 rounded-2xl border border-slate-200/80 bg-slate-50/80 p-4 text-sm text-slate-600">
          <p><strong className="text-slate-900">Etapa 1:</strong> ponto principal, critérios e enriquecimentos.</p>
          <p><strong className="text-slate-900">Etapas 2 a 4:</strong> transporte, geração de zonas e detalhamento urbano.</p>
          <p><strong className="text-slate-900">Etapas 5 e 6:</strong> busca, comparação e leitura analítica do mercado local.</p>
        </div>
        <div className="mt-4 text-right">
          <button
            type="button"
            onClick={onClose}
            className="gem-primary-button"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
