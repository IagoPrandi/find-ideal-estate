import { Loader2 } from "lucide-react";

type LoadingProps = {
  visible: boolean;
  loadingText: string;
  mapBusyMessage: string;
};

export function MapLoadingOverlay({ visible, loadingText, mapBusyMessage }: LoadingProps) {
  if (!visible) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute inset-0 z-50 flex flex-col items-center justify-center bg-white/40 backdrop-blur-[3px]">
      <div className="pointer-events-auto flex max-w-sm flex-col items-center rounded-2xl border border-slate-200 bg-white/95 px-8 py-6 text-center shadow-2xl">
        <Loader2 className="mb-4 h-10 w-10 animate-spin text-pastel-violet-500" />
        <h3 className="mb-2 text-lg font-bold text-slate-800">Processando...</h3>
        <p className="text-sm font-medium leading-relaxed text-slate-500">{loadingText || mapBusyMessage || "Aguarde..."}</p>
      </div>
    </div>
  );
}

type ErrorProps = {
  message: string | null;
};

export function MapErrorOverlay({ message }: ErrorProps) {
  if (!message) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute inset-0 z-30 grid place-items-center bg-slate-950/35 p-6">
      <div className="pointer-events-auto max-w-md rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 shadow-lg">{message}</div>
    </div>
  );
}
