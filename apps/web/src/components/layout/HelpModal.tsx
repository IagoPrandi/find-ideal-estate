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
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <h2 id="help-modal-title" className="text-lg font-semibold text-slate-800">
          Ajuda
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Selecione um ponto principal no mapa, ajuste o modo Alugar/Comprar e use “Gerar Zonas Candidatas” para iniciar o
          run no backend.
        </p>
        <p className="mt-3 text-sm text-slate-500">
          Interesses são opcionais e não entram como seed de geração de zonas. O painel mostra o status de execução e as
          ações do fluxo em 3 etapas.
        </p>
        <div className="mt-4 text-right">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-pastel-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-pastel-violet-600"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
