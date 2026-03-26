import { formatMeters } from "../../lib/formatTransport";
import type { ListingSortMode, Step3ComparisonExtremes } from "./types";
import { getComparisonCellClass, resolveRawListingText } from "./step3Helpers";
import type { ListingFeature, Step3SortedListingRow } from "./step3Types";

export type Step3FinalListingsSectionProps = {
  finalizeMessage: string;
  freshnessBadgeText: string;
  listingDiffMessage: string;
  runId: string;
  apiBase: string;
  finalListings: ListingFeature[];
  listingSortMode: ListingSortMode;
  onListingSortModeChange: (mode: ListingSortMode) => void;
  poiCountRadiusM: number;
  onPoiCountRadiusChange: (m: number) => void;
  selectedListingsForComparison: Step3SortedListingRow[];
  comparisonExtremes: Step3ComparisonExtremes;
  sortedListings: Step3SortedListingRow[];
  onListingCardClick: (feature: ListingFeature, index: number) => void;
  selectedListingKeys: string[];
  newlyAddedListingKeys: string[];
  listingsWithoutCoords: Array<Record<string, unknown>>;
  parseFiniteNumber: (value: unknown) => number | null;
  formatCurrencyBr: (value: unknown) => string;
};

export function Step3FinalListingsSection({
  finalizeMessage,
  freshnessBadgeText,
  listingDiffMessage,
  finalListings,
  listingSortMode,
  onListingSortModeChange,
  poiCountRadiusM,
  onPoiCountRadiusChange,
  selectedListingsForComparison,
  comparisonExtremes,
  sortedListings,
  onListingCardClick,
  selectedListingKeys,
  newlyAddedListingKeys,
  listingsWithoutCoords,
  parseFiniteNumber,
  formatCurrencyBr
}: Step3FinalListingsSectionProps) {
  return (
    <section className="gem-panel-section animate-[fadeInRight_0.4s_ease-out] text-sm">
      <div className="gem-panel-header">
        <p className="gem-eyebrow">Etapa 6</p>
        <h2 className="gem-title mt-1">Imóveis finais da zona</h2>
        <p className="gem-subtitle mt-1">Use ordenação, comparação e POIs próximos para decidir com base em critérios objetivos.</p>
      </div>
      <div className="gem-panel-body">
      <p className="text-xs text-slate-500">{finalizeMessage}</p>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
        <span className="gem-chip">{freshnessBadgeText}</span>
        {listingDiffMessage ? (
          <span className="gem-chip border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-600">
            {listingDiffMessage}
          </span>
        ) : null}
      </div>

      <div className="mt-2 rounded-2xl border border-slate-200/80 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        Export desabilitado durante a migração para `journeys/jobs`.
      </div>

      {finalListings.length > 0 ? (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <label className="col-span-2">
              <span className="mb-1 block text-[11px] font-semibold text-slate-500">Ordenar imóveis</span>
              <select
                value={listingSortMode}
                onChange={(event) => onListingSortModeChange(event.target.value as ListingSortMode)}
                className="gem-select"
              >
                <option value="price-asc">Preço (menor → maior)</option>
                <option value="price-desc">Preço (maior → menor)</option>
                <option value="size-desc">Tamanho (maior → menor)</option>
                <option value="size-asc">Tamanho (menor → maior)</option>
              </select>
            </label>
            <label className="col-span-2">
              <span className="mb-1 block text-[11px] font-semibold text-slate-500">Raio para contagem de POIs (m)</span>
              <input
                type="number"
                min={100}
                step={50}
                value={poiCountRadiusM}
                onChange={(event) => onPoiCountRadiusChange(Math.max(100, Number(event.target.value) || 100))}
                className="gem-input"
              />
            </label>
          </div>

          {selectedListingsForComparison.length > 1 ? (
            <div className="mt-3 rounded-[22px] border border-slate-200/80 bg-slate-50 px-3 py-3 text-xs">
              <h3 className="font-semibold text-slate-800">Comparação ({selectedListingsForComparison.length} imóveis)</h3>
              <p className="mt-1 text-slate-500">
                Comparando preço, tamanho, distância de transporte e POIs em até {poiCountRadiusM} m.
              </p>
              <div className="mt-2 overflow-x-auto">
                <table className="min-w-[760px] w-full border-collapse text-[11px]">
                  <thead>
                    <tr>
                      <th className="border border-slate-200 bg-white px-2 py-1.5 text-left font-semibold text-slate-800">
                        Métrica
                      </th>
                      {selectedListingsForComparison.map((item, idx) => (
                        <th
                          key={`cmp_head_${item.analytics.listingKey}`}
                          className="border border-slate-200 bg-white px-2 py-1.5 text-left font-semibold text-slate-800"
                        >
                          Imóvel {idx + 1}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">Preço</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_price_${item.analytics.listingKey}`}
                          className={`border border-slate-200 px-2 py-1 ${getComparisonCellClass(
                            item.analytics.priceValue,
                            comparisonExtremes.price.min,
                            comparisonExtremes.price.max,
                            "lower-better"
                          )}`}
                        >
                          {item.info.priceLabel}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">Plataforma</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_platform_${item.analytics.listingKey}`}
                          className="border border-slate-200 px-2 py-1 text-slate-800"
                        >
                          {item.analytics.platform}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">Endereço</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_address_${item.analytics.listingKey}`}
                          className="border border-slate-200 px-2 py-1 text-slate-800"
                        >
                          {item.info.address}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">Tamanho</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_size_${item.analytics.listingKey}`}
                          className={`border border-slate-200 px-2 py-1 ${getComparisonCellClass(
                            item.analytics.sizeM2,
                            comparisonExtremes.size.min,
                            comparisonExtremes.size.max,
                            "higher-better"
                          )}`}
                        >
                          {item.analytics.sizeM2 ? `${item.analytics.sizeM2.toFixed(0)} m²` : "n/d"}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">Quartos</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_beds_${item.analytics.listingKey}`}
                          className="border border-slate-200 px-2 py-1 text-slate-800"
                        >
                          {item.analytics.bedrooms ? `${item.analytics.bedrooms}` : "n/d"}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">Transporte mais próximo</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_transport_${item.analytics.listingKey}`}
                          className={`border border-slate-200 px-2 py-1 ${getComparisonCellClass(
                            item.analytics.distanceTransportM,
                            comparisonExtremes.transport.min,
                            comparisonExtremes.transport.max,
                            "lower-better"
                          )}`}
                        >
                          {formatMeters(item.analytics.distanceTransportM)}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="border border-slate-200 px-2 py-1 text-slate-500">POIs até {poiCountRadiusM} m</td>
                      {selectedListingsForComparison.map((item) => (
                        <td
                          key={`cmp_poi_count_${item.analytics.listingKey}`}
                          className={`border border-slate-200 px-2 py-1 ${getComparisonCellClass(
                            item.analytics.poiCountWithinRadius,
                            comparisonExtremes.poiCount.min,
                            comparisonExtremes.poiCount.max,
                            "higher-better"
                          )}`}
                        >
                          {item.analytics.poiCountWithinRadius}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          <ul className="mt-3 space-y-2.5">
            {sortedListings.map(({ feature, index, info, analytics }) => {
              const isSelected = selectedListingKeys.includes(analytics.listingKey);
              const isRecentlyAdded = newlyAddedListingKeys.includes(analytics.listingKey);
              return (
                <li
                  key={analytics.listingKey}
                  className={`cursor-pointer rounded-[22px] border px-4 py-4 text-xs transition hover:border-pastel-violet-400 hover:shadow-md ${
                    isSelected ? "border-pastel-violet-300 bg-pastel-violet-50/60 shadow-sm" : "border-slate-200 bg-white"
                  } ${isRecentlyAdded ? "bg-emerald-50" : ""}`}
                  onClick={() => onListingCardClick(feature, index)}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-base font-extrabold text-slate-900">{info.priceLabel}</p>
                      <p className="mt-1 text-slate-500">Plataforma: {analytics.platform}</p>
                      <p className="text-slate-500">{info.address}</p>
                    </div>
                    <span className="gem-chip">{freshnessBadgeText}</span>
                  </div>
                  <p className="mt-3 text-slate-500">
                    Tamanho: {analytics.sizeM2 ? `${analytics.sizeM2.toFixed(0)} m²` : "n/d"} · Quartos:{" "}
                    {analytics.bedrooms ? `${analytics.bedrooms}` : "n/d"}
                  </p>
                  {info.url ? (
                    <a href={info.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-pastel-violet-600 underline">
                      Abrir anúncio
                    </a>
                  ) : null}
                  {isSelected ? (
                    <div className="mt-3 rounded-2xl border border-slate-200/80 bg-white px-3 py-3 text-[11px] text-slate-500">
                      <p className="font-semibold text-slate-800">Distâncias para POIs de maior interesse</p>
                      <ul className="mt-1 space-y-0.5">
                        {analytics.nearestPoiByCategory.length > 0 ? (
                          analytics.nearestPoiByCategory.map((poi) => (
                            <li key={`${analytics.listingKey}_${poi.category}`}>
                              {poi.category}: {formatMeters(poi.distanceM)}
                            </li>
                          ))
                        ) : (
                          <li>Sem dados de POI para comparação.</li>
                        )}
                      </ul>
                      <p className="mt-1">
                        POIs até {poiCountRadiusM} m: {analytics.poiCountWithinRadius}
                      </p>
                      <p className="mt-1">Transporte mais próximo: {formatMeters(analytics.distanceTransportM)}</p>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}

      {listingsWithoutCoords.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-slate-200/80 bg-slate-50 px-3 py-3 text-xs">
          <h3 className="font-semibold text-slate-800">Sem localização no mapa ({listingsWithoutCoords.length})</h3>
          <ul className="mt-2 space-y-2">
            {listingsWithoutCoords.map((item, index) => {
              const info = resolveRawListingText(item, formatCurrencyBr);
              return (
                <li key={`without_coords_${index}`} className="rounded-2xl border border-slate-200 bg-white px-3 py-3">
                  <p className="font-semibold text-slate-800">{info.priceLabel}</p>
                  <p className="text-slate-500">
                    Plataforma: {String(item.source || item.platform || item.site || "PLATAFORMA N/D").toUpperCase()}
                  </p>
                  <p className="text-slate-500">{info.address}</p>
                  <p className="text-slate-500">
                    Tamanho: {parseFiniteNumber(item.area_m2 ?? item.area ?? item.private_area ?? item.usable_area)?.toFixed(0) || "n/d"}{" "}
                    m² · Quartos: {parseFiniteNumber(item.beds ?? item.bedrooms ?? item.quartos)?.toFixed(0) || "n/d"}
                  </p>
                  {info.url ? (
                    <a href={info.url} target="_blank" rel="noreferrer" className="text-pastel-violet-600 underline">
                      Abrir anúncio
                    </a>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      </div>
    </section>
  );
}
