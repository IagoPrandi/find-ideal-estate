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
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <h2 className="font-semibold">Buscar imóveis</h2>
      <div className="mt-2 space-y-2">
        <label className="block">
          <span className="mb-1 block text-[11px] text-slate-500">
            Endereço da busca (autocomplete da zona: bairros {">"} logradouros {">"} referências)
          </span>
          <input
            value={streetQuery}
            onChange={(event) => onStreetQueryChange(event.target.value)}
            placeholder="Digite bairro, rua ou referência"
            className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
          />
        </label>

        <p className="text-[11px] text-slate-500">
          A busca fica habilitada apenas depois da seleção de uma sugestão válida.
          {selectedStreetType ? ` Selecionado: ${suggestionTypeLabel[selectedStreetType]}.` : ""}
        </p>
        <div className="grid grid-cols-1 gap-2">
          <button
            type="button"
            aria-label="Buscar imóveis"
            onClick={onZoneListings}
            disabled={!selectedZoneUid || !zoneDetailData || isListingZone || !selectedStreet}
            className="rounded border border-slate-200 px-2 py-1.5 text-xs font-semibold disabled:opacity-50"
          >
            {isListingZone ? "Buscando..." : "Buscar imóveis"}
          </button>
        </div>

        {streetSuggestions.length > 0 ? (
          <ul
            data-testid="street-suggestions-ul"
            className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200/80 bg-slate-50 p-2"
          >
            {streetSuggestions.map((item) => {
              const isSelected = selectedStreet === item.label;
              return (
                <li key={`${item.type}:${item.normalized}`}>
                  <button
                    type="button"
                    onClick={() => onStreetSuggestionSelect(item)}
                    className={`w-full rounded-md px-2 py-1.5 text-left text-xs ${
                      isSelected ? "bg-pastel-violet-500/10 text-pastel-violet-600" : "hover:bg-white"
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
      </div>
      <p className="mt-2 text-xs text-slate-500">{zoneListingMessage}</p>
      <p className="mt-1 text-xs text-slate-500">{finalizeMessage}</p>
    </section>
  );
}
