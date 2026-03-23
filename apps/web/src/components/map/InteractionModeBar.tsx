export type InteractionMode = "primary" | "interest";

type Props = {
  mode: InteractionMode;
  onModeChange: (mode: InteractionMode) => void;
};

export function InteractionModeBar({ mode, onModeChange }: Props) {
  return (
    <div className="pointer-events-auto absolute left-1/2 top-[88px] z-40 flex -translate-x-1/2 flex-wrap justify-center gap-2">
      <button
        type="button"
        onClick={() => onModeChange("primary")}
        className={`rounded-xl px-3 py-2 text-xs font-semibold shadow-sm transition ${
          mode === "primary"
            ? "bg-pastel-violet-500 text-white shadow-pastel-violet-200"
            : "border border-slate-200 bg-white/95 text-slate-500"
        }`}
      >
        Definir principal
      </button>
      <button
        type="button"
        onClick={() => onModeChange("interest")}
        className={`rounded-xl px-3 py-2 text-xs font-semibold shadow-sm transition ${
          mode === "interest"
            ? "bg-pastel-violet-500 text-white shadow-pastel-violet-200"
            : "border border-slate-200 bg-white/95 text-slate-500"
        }`}
      >
        Adicionar interesse
      </button>
    </div>
  );
}
