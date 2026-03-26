export type Step3PanelTabBarProps = {
  activePanelTab: "listings" | "dashboard";
  onActivePanelTabChange: (tab: "listings" | "dashboard") => void;
};

export function Step3PanelTabBar({ activePanelTab, onActivePanelTabChange }: Step3PanelTabBarProps) {
  return (
    <section className="gem-panel-section animate-[fadeIn_0.3s_ease-out] text-sm">
      <div className="gem-panel-header pb-0">
        <p className="gem-eyebrow">Etapa 6</p>
        <h3 className="gem-title mt-1">Resultados consolidados</h3>
        <p className="gem-subtitle mt-1">Alterne entre imóveis detalhados e dashboard analítico da zona.</p>
        <div className="mt-4 flex gap-6 border-b border-transparent">
        <button
          type="button"
          onClick={() => onActivePanelTabChange("listings")}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors ${
            activePanelTab === "listings"
              ? "border-pastel-violet-500 text-pastel-violet-600"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          Imóveis
        </button>
        <button
          type="button"
          onClick={() => onActivePanelTabChange("dashboard")}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors ${
            activePanelTab === "dashboard"
              ? "border-pastel-violet-500 text-pastel-violet-600"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          Dashboard
        </button>
      </div>
      </div>
    </section>
  );
}
