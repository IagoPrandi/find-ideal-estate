import { Info, MapPin, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { apiActionHint, getZoneAddressSuggestions, searchZoneListings } from "../../api/client";
import type { SearchAddressSuggestion } from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";

export function Step5Address() {
  const listboxId = "zone-address-combobox-listbox";
  const inputId = "zone-address-combobox-input";
  const journeyId = useJourneyStore((state) => state.journeyId);
  const zoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const config = useJourneyStore((state) => state.config);
  const addressQuery = useJourneyStore((state) => state.addressQuery);
  const selectedAddress = useJourneyStore((state) => state.selectedAddress);
  const setAddressQuery = useJourneyStore((state) => state.setAddressQuery);
  const setSelectedAddress = useJourneyStore((state) => state.setSelectedAddress);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [suggestions, setSuggestions] = useState<SearchAddressSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  function selectSuggestion(suggestion: SearchAddressSuggestion) {
    setSelectedAddress({
      label: suggestion.label,
      normalized: suggestion.normalized,
      locationType: suggestion.location_type,
      lat: suggestion.lat,
      lon: suggestion.lon
    });
    setAddressQuery(suggestion.label);
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
    setIsDropdownOpen(false);
    setError(null);
  }

  useEffect(() => {
    if (!journeyId || !zoneFingerprint) {
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      setIsDropdownOpen(false);
      return;
    }

    if (!isDropdownOpen) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setLoadingSuggestions(true);
      void getZoneAddressSuggestions(journeyId, zoneFingerprint, addressQuery.trim())
        .then((items) => {
          setSuggestions(items);
          setActiveSuggestionIndex(items.length > 0 ? 0 : -1);
          setIsDropdownOpen(true);
          setError(null);
        })
        .catch((caughtError) => {
          setSuggestions([]);
          setActiveSuggestionIndex(-1);
          setIsDropdownOpen(true);
          setError(apiActionHint(caughtError));
        })
        .finally(() => setLoadingSuggestions(false));
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [addressQuery, isDropdownOpen, journeyId, zoneFingerprint]);

  async function handleSubmit() {
    if (!journeyId || !zoneFingerprint || !selectedAddress) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await searchZoneListings(journeyId, zoneFingerprint, {
        search_location_normalized: selectedAddress.normalized,
        search_location_label: selectedAddress.label,
        search_location_type: selectedAddress.locationType,
        search_type: config.type,
        usage_type: "residential"
      });
      setMaxStep(6);
      goToStep(6);
    } catch (caughtError) {
      setError(apiActionHint(caughtError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-full flex-col animate-[fadeInUp_0.3s_ease-out]">
      <div className="border-b border-slate-100 p-5">
        <h2 className="text-xl font-semibold tracking-tight text-slate-800">Refinar Busca</h2>
        <p className="text-sm text-slate-500">Escolha um logradouro ou ponto contido no polígono da zona selecionada.</p>
      </div>

      <div className="panel-scroll flex-1 space-y-6 overflow-y-auto p-5">
        <div className="flex items-start gap-3 rounded-xl border border-pastel-violet-100 bg-pastel-violet-50 p-4 text-sm text-pastel-violet-800">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-pastel-violet-500" />
          <p>Ao clicar no campo, a lista mostra as ruas encontradas dentro da zona selecionada. Se quiser, digite para filtrar essa lista.</p>
        </div>

        <div className="space-y-2">
          <label htmlFor={inputId} className="text-sm font-medium text-slate-700">Endereço alvo na zona</label>
          <div className="relative">
            <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id={inputId}
              type="text"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={isDropdownOpen}
              aria-controls={listboxId}
              aria-activedescendant={activeSuggestionIndex >= 0 ? `${listboxId}-${activeSuggestionIndex}` : undefined}
              value={addressQuery}
              onChange={(event) => {
                setAddressQuery(event.target.value);
                setSelectedAddress(null);
                setActiveSuggestionIndex(-1);
                setIsDropdownOpen(true);
              }}
              onFocus={() => {
                if (journeyId && zoneFingerprint) {
                  setIsDropdownOpen(true);
                }
              }}
              onBlur={() => {
                window.setTimeout(() => {
                  setIsDropdownOpen(false);
                  setActiveSuggestionIndex(-1);
                }, 120);
              }}
              onKeyDown={(event) => {
                if (!isDropdownOpen && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
                  event.preventDefault();
                  setIsDropdownOpen(true);
                }
                if (suggestions.length === 0) {
                  return;
                }
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setActiveSuggestionIndex((current) => (current + 1) % suggestions.length);
                  return;
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setActiveSuggestionIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
                  return;
                }
                if (event.key === "Enter") {
                  if (activeSuggestionIndex >= 0 && activeSuggestionIndex < suggestions.length) {
                    event.preventDefault();
                    selectSuggestion(suggestions[activeSuggestionIndex]);
                  }
                  return;
                }
                if (event.key === "Escape") {
                  setSuggestions([]);
                  setActiveSuggestionIndex(-1);
                  setIsDropdownOpen(false);
                }
              }}
              placeholder="Clique para ver ou digite para filtrar as ruas da zona"
              className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4 shadow-sm outline-none transition-all focus:border-pastel-violet-400 focus:ring-2 focus:ring-pastel-violet-400"
            />
            {isDropdownOpen ? (
              <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_18px_48px_rgba(15,23,42,0.16)] animate-[fadeInDown_0.18s_ease-out]">
                {loadingSuggestions ? <p className="px-4 py-3 text-xs text-slate-400">Carregando ruas da zona...</p> : null}

                {!loadingSuggestions && suggestions.length > 0 ? (
                  <div id={listboxId} role="listbox" className="max-h-72 overflow-y-auto py-1" data-testid="zone-street-suggestions">
                    {suggestions.map((suggestion, index) => (
                      <button
                        id={`${listboxId}-${index}`}
                        key={`${suggestion.normalized}-${suggestion.lat}-${suggestion.lon}`}
                        type="button"
                        role="option"
                        aria-selected={index === activeSuggestionIndex}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectSuggestion(suggestion)}
                        className={`flex w-full items-center gap-2 px-4 py-3 text-left text-sm transition-colors ${index === activeSuggestionIndex ? "bg-pastel-violet-50 text-pastel-violet-900" : "hover:bg-slate-50"}`}
                      >
                        <MapPin className="h-3.5 w-3.5 text-slate-400" />
                        <span>{suggestion.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}

                {!loadingSuggestions && suggestions.length === 0 ? (
                  <p className="px-4 py-3 text-xs text-slate-500">Nenhuma rua encontrada dentro da zona selecionada.</p>
                ) : null}
              </div>
            ) : null}
          </div>

          {selectedAddress ? <p className="text-xs font-medium text-emerald-700">Selecionado: {selectedAddress.label}</p> : null}
        </div>

        {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
      </div>

      <div className="border-t border-slate-100 bg-white p-5">
        <button type="button" onClick={handleSubmit} disabled={!selectedAddress || submitting} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400">
          {submitting ? "Enfileirando busca..." : "Iniciar scraping e ver resultados"}
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}