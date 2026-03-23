import { HelpCircle, Layers, Minus, Plus, X } from "lucide-react";
import { MAP_LAYER_INFO, type MapLayerKey } from "../../domain/mapLayers";

type Props = {
  rightOffsetClass: string;
  isLayerMenuOpen: boolean;
  onLayerMenuToggle: () => void;
  onLayerMenuClose: () => void;
  layerVisibility: Record<MapLayerKey, boolean>;
  onToggleLayer: (key: MapLayerKey) => void;
  hasRouteData: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onOpenHelp: () => void;
};

export function MapToolbarRight({
  rightOffsetClass,
  isLayerMenuOpen,
  onLayerMenuToggle,
  onLayerMenuClose,
  layerVisibility,
  onToggleLayer,
  hasRouteData,
  onZoomIn,
  onZoomOut,
  onOpenHelp
}: Props) {
  return (
    <div className={`pointer-events-auto absolute bottom-6 z-40 flex flex-col items-end justify-end gap-2 ${rightOffsetClass}`}>
      <button
        type="button"
        onClick={onLayerMenuToggle}
        aria-label="Camadas"
        className={`pointer-events-auto flex items-center justify-end gap-2 rounded-xl border bg-white/95 px-4 py-2.5 font-bold text-slate-700 shadow-md backdrop-blur-md transition-all ${
          isLayerMenuOpen ? "border-pastel-violet-400 text-pastel-violet-600" : "border-slate-200"
        }`}
      >
        <Layers className="h-5 w-5" />
      </button>
      {isLayerMenuOpen ? (
        <div className="pointer-events-auto absolute bottom-full right-0 mb-2 w-48 rounded-xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur-md">
          <div className="mb-3 flex items-center justify-between text-xs font-bold uppercase text-slate-800">
            Camadas Visíveis
            <button type="button" onClick={onLayerMenuClose} className="text-slate-400 hover:text-slate-700">
              <X size={16} />
            </button>
          </div>
          {(Object.keys(MAP_LAYER_INFO) as MapLayerKey[]).map((key) => (
            <label key={key} className="group mb-3 flex cursor-pointer items-center gap-2.5">
              <input
                type="checkbox"
                checked={layerVisibility[key]}
                onChange={() => onToggleLayer(key)}
                className="h-4 w-4 rounded accent-pastel-violet-500"
              />
              <span
                className={`text-sm font-medium ${(key === "routes" || key === "train") && !hasRouteData ? "text-slate-400" : "text-slate-700"}`}
              >
                {MAP_LAYER_INFO[key].label}
              </span>
            </label>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white/95 shadow-lg backdrop-blur-md">
        <button
          type="button"
          onClick={onZoomIn}
          className="border-b border-slate-100 p-2 text-slate-600 transition-colors hover:bg-slate-50 hover:text-pastel-violet-600"
          title="Aumentar zoom"
        >
          <Plus size={20} />
        </button>
        <button
          type="button"
          onClick={onZoomOut}
          className="p-2 text-slate-600 transition-colors hover:bg-slate-50 hover:text-pastel-violet-600"
          title="Diminuir zoom"
        >
          <Minus size={20} />
        </button>
      </div>
      <button
        type="button"
        onClick={onOpenHelp}
        className="rounded-xl border border-slate-200 bg-white/95 p-2 text-slate-600 shadow-lg backdrop-blur-md transition-colors hover:bg-slate-50 hover:text-pastel-violet-600"
        title="Ajuda"
      >
        <HelpCircle size={20} />
      </button>
    </div>
  );
}
