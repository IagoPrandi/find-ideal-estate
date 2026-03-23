export type Step3PanelTabBarProps = {
  activePanelTab: "listings" | "dashboard";
  onActivePanelTabChange: (tab: "listings" | "dashboard") => void;
};

export function Step3PanelTabBar({ activePanelTab, onActivePanelTabChange }: Step3PanelTabBarProps) {
  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-3 text-sm shadow-sm">
      <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1">
        <button
          type="button"
          onClick={() => onActivePanelTabChange("listings")}
          className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
            activePanelTab === "listings" ? "bg-pastel-violet-500 text-white" : "text-slate-500"
          }`}
        >
          Imóveis
        </button>
        <button
          type="button"
          onClick={() => onActivePanelTabChange("dashboard")}
          className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
            activePanelTab === "dashboard" ? "bg-pastel-violet-500 text-white" : "text-slate-500"
          }`}
        >
          Dashboard
        </button>
      </div>
    </section>
  );
}
