"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Etapa5Props = {
  journeyId: string;
  zoneFingerprint: string;
  zoneLabel: string;
  searchType: "rent" | "buy";
  onListingsReady: (result: ListingsRequestResult) => void;
};

type AddressSuggestion = {
  label: string;
  normalized: string;
  location_type: string;
  lat: number;
  lon: number;
};

type ListingsRequestResult = {
  source: "cache" | "none" | "scraping";
  freshness_status?: string;
  upgrade_reason?: string;
  next_refresh_window?: string;
  listings: unknown[];
  total_count: number;
  cache_age_hours?: number;
  job_id?: string;
};

export function Etapa5ListingsSearch({
  journeyId,
  zoneFingerprint,
  zoneLabel,
  searchType,
  onListingsReady,
}: Etapa5Props) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [selectedSuggestion, setSelectedSuggestion] = useState<AddressSuggestion | null>(null);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchSuggestions = useCallback(
    async (q: string) => {
      if (q.length < 2) {
        setSuggestions([]);
        setShowDropdown(false);
        return;
      }
      setIsLoadingSuggestions(true);
      try {
        const params = new URLSearchParams({
          zone_fingerprint: zoneFingerprint,
          q,
        });
        const res = await fetch(
          `/api/journeys/${journeyId}/listings/address-suggest?${params.toString()}`,
          { cache: "no-store" },
        );
        if (!res.ok) throw new Error("Falha ao buscar sugestões");
        const data = (await res.json()) as AddressSuggestion[];
        setSuggestions(data);
        setShowDropdown(data.length > 0);
      } catch {
        setSuggestions([]);
      } finally {
        setIsLoadingSuggestions(false);
      }
    },
    [journeyId, zoneFingerprint],
  );

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    setSelectedSuggestion(null);
    setError(null);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(val), 300);
  };

  const handleSelectSuggestion = (sug: AddressSuggestion) => {
    setSelectedSuggestion(sug);
    setQuery(sug.label);
    setShowDropdown(false);
    setSuggestions([]);
  };

  const handleSearch = useCallback(async () => {
    if (!selectedSuggestion) return;
    setIsSearching(true);
    setError(null);

    try {
      const res = await fetch(`/api/journeys/${journeyId}/listings/search`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          zone_fingerprint: zoneFingerprint,
          search_location_normalized: selectedSuggestion.normalized,
          search_location_label: selectedSuggestion.label,
          search_location_type: selectedSuggestion.location_type,
          search_type: searchType === "rent" ? "rent" : "sale",
          usage_type: "residential",
        }),
      });

      if (!res.ok) throw new Error("Falha ao buscar imóveis");
      const result = (await res.json()) as ListingsRequestResult;
      onListingsReady(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
    } finally {
      setIsSearching(false);
    }
  }, [journeyId, selectedSuggestion, zoneFingerprint, searchType, onListingsReady]);

  const locationTypeLabel: Record<string, string> = {
    neighborhood: "Bairro",
    street: "Rua",
    address: "Endereço",
    landmark: "Referência",
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="space-y-1">
        <h2 className="text-base font-semibold text-gray-900">Buscar imóveis</h2>
        <p className="text-sm text-gray-500">
          Zona: <span className="font-medium text-gray-700">{zoneLabel}</span>
        </p>
        <p className="text-xs text-gray-400">
          Selecione um logradouro dentro da zona para buscar imóveis próximos.
        </p>
      </div>

      <div ref={containerRef} className="relative">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={handleQueryChange}
            onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
            placeholder="Digite o nome da rua ou bairro…"
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 pr-8 text-sm
                       shadow-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {isLoadingSuggestions && (
            <div className="absolute right-2 top-1/2 -translate-y-1/2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            </div>
          )}
        </div>

        {showDropdown && suggestions.length > 0 && (
          <ul className="absolute z-50 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border
                         border-gray-200 bg-white shadow-lg">
            {suggestions.map((sug, i) => (
              <li
                key={i}
                onMouseDown={() => handleSelectSuggestion(sug)}
                className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-blue-50"
              >
                <span className="inline-block rounded bg-gray-100 px-1.5 py-0.5 text-[10px]
                                 font-medium uppercase tracking-wide text-gray-500">
                  {locationTypeLabel[sug.location_type] ?? sug.location_type}
                </span>
                <span className="text-sm text-gray-800">{sug.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      <button
        onClick={handleSearch}
        disabled={!selectedSuggestion || isSearching}
        className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white
                   shadow-sm transition-colors hover:bg-blue-700 active:bg-blue-800
                   disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isSearching ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2
                             border-white border-t-transparent" />
            Buscando…
          </span>
        ) : (
          "Buscar imóveis"
        )}
      </button>

      <p className="text-xs text-gray-400 text-center">
        Imóveis disponíveis via cache pré-aquecido · atualizado às 03:00
      </p>
    </div>
  );
}
