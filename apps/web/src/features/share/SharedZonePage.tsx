import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, MapPin } from "lucide-react";
import { apiActionHint, getZoneFavoriteShare } from "../../api/client";
import { getPoiCategoryMeta } from "../../domain/poi";
import { formatCurrencyBr, resolvePlatformUrl } from "../../lib/listingFormat";

type SharedZonePageProps = {
  token: string;
};

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 text-sm">
      <span className="font-medium text-slate-500">{label}</span>
      <span className="font-semibold text-slate-900">{value}</span>
    </div>
  );
}

export function SharedZonePage({ token }: SharedZonePageProps) {
  const query = useQuery({
    queryKey: ["shared-zone", token],
    queryFn: async () => getZoneFavoriteShare(token),
    retry: false,
  });

  const zone = query.data;
  const metrics = zone?.payload.metrics || {};
  const transport = zone?.payload.transport_summary;
  const propertyTypes = useMemo(
    () => Object.entries(zone?.payload.property_type_counts || {}).filter(([, count]) => Number(count) > 0),
    [zone?.payload.property_type_counts],
  );

  if (query.isLoading) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">Carregando zona compartilhada...</main>;
  }

  if (query.error || !zone) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="max-w-md rounded-2xl border border-rose-200 bg-white p-6 text-sm text-rose-700 shadow-sm">
          {apiActionHint(query.error || new Error("Compartilhamento não encontrado."))}
        </div>
      </main>
    );
  }

  const zoneName = zone.payload.neighborhood_name
    ? `${zone.payload.neighborhood_name}${zone.payload.city_name ? ` · ${zone.payload.city_name}` : ""}`
    : `Zona ${zone.zoneFingerprint.slice(0, 8)}`;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900">
      <div className="mx-auto max-w-5xl space-y-5">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Zona compartilhada</p>
              <h1 className="mt-2 text-2xl font-bold tracking-tight">{zoneName}</h1>
              <p className="mt-1 text-sm text-slate-500">Visualização somente leitura.</p>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700">
              <span className="h-4 w-4 rounded-full" style={{ backgroundColor: zone.color }} />
              {zone.color}
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900">Métricas</h2>
            <div className="mt-4 grid gap-2">
              <MetricRow label="Tempo" value={metrics.travel_time_minutes != null ? `${metrics.travel_time_minutes} min` : "--"} />
              <MetricRow label="Área" value={metrics.zone_area_m2 != null ? `${(metrics.zone_area_m2 / 1_000_000).toFixed(2)} km²` : "--"} />
              <MetricRow label="Verde" value={metrics.green_percentage != null ? `${metrics.green_percentage.toFixed(1)}%` : "--"} />
              <MetricRow label="Alagamento" value={metrics.flood_percentage != null ? `${metrics.flood_percentage.toFixed(1)}%` : "--"} />
              <MetricRow label="Preço médio" value={metrics.zone_average_price != null ? formatCurrencyBr(metrics.zone_average_price) : "--"} />
              <MetricRow label="Preço m²" value={metrics.zone_average_unit_price != null ? `${formatCurrencyBr(metrics.zone_average_unit_price)}/m²` : "--"} />
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900">Transporte e imóveis</h2>
            <div className="mt-4 grid gap-2">
              <MetricRow label="Pontos de ônibus" value={String(transport?.bus_stop_count ?? 0)} />
              <MetricRow label="Linhas de ônibus" value={String(transport?.bus_line_count ?? 0)} />
              <MetricRow label="Terminais" value={String(transport?.bus_terminal_count ?? 0)} />
              <MetricRow label="Estações trem/metrô" value={String(transport?.train_metro_platform_count ?? 0)} />
              <MetricRow label="Linhas trem/metrô" value={String(transport?.train_metro_line_count ?? 0)} />
              {propertyTypes.map(([type, count]) => (
                <MetricRow key={type} label={type === "residential" ? "Residenciais" : type === "commercial" ? "Comerciais" : type} value={String(count)} />
              ))}
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-slate-900">Pontos de interesse</h2>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {(zone.payload.poi_points || []).length === 0 ? <p className="text-sm text-slate-500">Nenhum ponto de interesse salvo no snapshot.</p> : null}
            {(zone.payload.poi_points || []).map((poi, index) => {
              const meta = getPoiCategoryMeta(poi.category);
              return (
                <div key={`${poi.id || index}`} className="flex items-start gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <MapPin className="mt-0.5 h-4 w-4" style={{ color: meta.color }} />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{poi.name || "Ponto de interesse sem nome"}</p>
                    <p className="text-xs text-slate-500">{meta.label}{poi.address ? ` · ${poi.address}` : ""}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-slate-900">Imóveis salvos no snapshot</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(zone.payload.listings || []).length === 0 ? <p className="text-sm text-slate-500">Nenhum imóvel salvo no snapshot.</p> : null}
            {(zone.payload.listings || []).map((listing, index) => {
              const href = resolvePlatformUrl(listing.url, listing.platform);
              return (
                <article key={`${listing.property_id || listing.platform_listing_id || index}`} className="rounded-xl border border-slate-200 p-3">
                  <p className="text-sm font-semibold">{listing.address_normalized || "Endereço não informado"}</p>
                  <p className="mt-1 text-xs text-slate-500">{listing.neighborhood_name || "Bairro não informado"}</p>
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-pastel-violet-700 hover:text-pastel-violet-900">
                      Abrir anúncio
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
