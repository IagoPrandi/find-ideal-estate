import type { ZoneDetailResponse } from "../../api/schemas";
import type { SearchSuggestion, SearchSuggestionType } from "./types";

export type Step3SearchListingsSectionProps = {
  zoneDetailData: ZoneDetailResponse | null;
  selectedZoneUid: string;
  isListingZone: boolean;
  zoneListingMessage: string;
  finalizeMessage: string;
  streetQuery: string;
  onStreetQueryChange: (value: string) => void;
  streetSuggestions: SearchSuggestion[];
  selectedStreet: string;
  selectedStreetType: SearchSuggestionType | null;
  suggestionTypeLabel: Record<SearchSuggestionType, string>;
  onStreetSuggestionSelect: (item: SearchSuggestion) => void;
  onZoneListings: () => void;
};

export function Step3SearchListingsSection({
  zoneDetailData,
  selectedZoneUid,
  isListingZone,
  zoneListingMessage,
  finalizeMessage,
  streetQuery,
  onStreetQueryChange,
  streetSuggestions,
  selectedStreet,
  selectedStreetType,
  suggestionTypeLabel,
  onStreetSuggestionSelect,
  onZoneListings
}: Step3SearchListingsSectionProps) {
  return (
    <section className="gem-panel-section animate-[fadeInUp_0.3s_ease-out] text-sm">
      <div className="gem-panel-header">
        <p className="gem-eyebrow">Etapa 5</p>
        <h2 className="gem-title mt-1">Buscar imóveis dentro da zona</h2>
        <p className="gem-subtitle mt-1">Escolha um bairro, rua ou referência válidos do recorte selecionado antes de disparar a coleta.</p>
      </div>
      <div className="gem-panel-body space-y-3">
        <div className="rounded-2xl border border-pastel-violet-100 bg-pastel-violet-50 px-3 py-3 text-xs text-pastel-violet-700">
          Selecione uma sugestão do autocomplete para habilitar a busca. O filtro respeita apenas elementos dentro da zona ativa.
        </div>
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold text-slate-500">
            Endereço da busca (autocomplete da zona: bairros {">"} logradouros {">"} referências)
          </span>
          <input
            value={streetQuery}
            onChange={(event) => onStreetQueryChange(event.target.value)}
            placeholder="Digite bairro, rua ou referência"
            className="gem-input"
          />
        </label>

        <div className="gem-soft-card text-[11px] text-slate-500">
          A busca fica habilitada apenas depois da seleção de uma sugestão válida.
          {selectedStreetType ? ` Selecionado: ${suggestionTypeLabel[selectedStreetType]}.` : ""}
        </div>
        <div className="grid grid-cols-1 gap-2">
          <button
            type="button"
            aria-label="Buscar imóveis"
            onClick={onZoneListings}
            disabled={!selectedZoneUid || !zoneDetailData || isListingZone || !selectedStreet}
            className="gem-primary-button w-full justify-between disabled:opacity-50"
          >
            {isListingZone ? "Buscando..." : "Buscar imóveis"}
          </button>
        </div>

        {streetSuggestions.length > 0 ? (
          <ul
            data-testid="street-suggestions-ul"
            className="max-h-48 space-y-1 overflow-y-auto rounded-2xl border border-slate-200/80 bg-white p-2 shadow-sm"
          >
            {streetSuggestions.map((item) => {
              const isSelected = selectedStreet === item.label;
              return (
                <li key={`${item.type}:${item.normalized}`}>
                  <button
                    type="button"
                    onClick={() => onStreetSuggestionSelect(item)}
                    className={`w-full rounded-xl px-3 py-2 text-left text-xs transition ${
                      isSelected
                        ? "bg-pastel-violet-500/10 text-pastel-violet-600"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    <span className="font-semibold text-slate-800">{item.label}</span>
                    <span className="ml-2 text-[11px] text-slate-500">{suggestionTypeLabel[item.type]}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
        <p className="text-xs text-slate-500">{zoneListingMessage}</p>
        <p className="text-xs text-slate-500">{finalizeMessage}</p>
      </div>
    </section>
  );
}
