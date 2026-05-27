import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Loader2, MapPin, Train } from "lucide-react";
import { getJourneyShare } from "../../api/client";
import type { JourneyShareSnapshotRead } from "../../api/schemas";
import { formatCurrencyBr } from "../../lib/listingFormat";

type SharedJourneyPageProps = {
  token: string;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function getReferenceLabel(snapshot: JourneyShareSnapshotRead) {
  const referencePoint = snapshot.journey.input_snapshot?.reference_point;
  if (typeof referencePoint === "object" && referencePoint !== null && "label" in referencePoint) {
    const label = (referencePoint as { label?: unknown }).label;
    if (typeof label === "string" && label.trim()) {
      return label;
    }
  }
  return snapshot.journey.secondary_reference_label || "Ponto de referência";
}

function compactFingerprint(value: string) {
  return value.length > 10 ? value.slice(0, 10) : value;
}

function formatCount(value: number | null | undefined, singular: string, plural: string) {
  const count = value ?? 0;
  return `${new Intl.NumberFormat("pt-BR").format(count)} ${count === 1 ? singular : plural}`;
}

export function SharedJourneyPage({ token }: SharedJourneyPageProps) {
  const shareQuery = useQuery({
    queryKey: ["journey-share", token],
    queryFn: () => getJourneyShare(token),
    enabled: Boolean(token)
  });

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10 text-slate-800">
        <div className="w-full max-w-lg rounded-lg border border-rose-200 bg-white p-6 shadow-sm">
          <AlertTriangle className="h-6 w-6 text-rose-500" />
          <h1 className="mt-4 text-xl font-bold">Link inválido</h1>
          <p className="mt-2 text-sm text-slate-600">O link de compartilhamento não contém um token de jornada.</p>
        </div>
      </main>
    );
  }

  if (shareQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10 text-slate-800">
        <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <Loader2 className="h-5 w-5 animate-spin text-pastel-violet-600" />
          <span className="text-sm font-semibold">Carregando jornada compartilhada</span>
        </div>
      </main>
    );
  }

  if (shareQuery.isError || !shareQuery.data) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10 text-slate-800">
        <div className="w-full max-w-lg rounded-lg border border-rose-200 bg-white p-6 shadow-sm">
          <AlertTriangle className="h-6 w-6 text-rose-500" />
          <h1 className="mt-4 text-xl font-bold">Jornada indisponível</h1>
          <p className="mt-2 text-sm text-slate-600">
            O link pode ter sido revogado, expirado ou não existir mais.
          </p>
        </div>
      </main>
    );
  }

  const snapshot = shareQuery.data;
  const zones = snapshot.zones.zones;
  const completedCount = snapshot.zones.completed_count ?? zones.filter((zone) => zone.state === "complete").length;
  const referenceLabel = getReferenceLabel(snapshot);

  return (
    <main className="min-h-screen bg-slate-50 text-slate-800">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-5 sm:px-6">
          <button
            type="button"
            onClick={() => { window.location.hash = ""; }}
            className="inline-flex w-fit items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar ao app
          </button>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-pastel-violet-600">Jornada compartilhada</p>
              <h1 className="mt-2 text-2xl font-bold leading-tight text-slate-900 sm:text-3xl">{referenceLabel}</h1>
              <p className="mt-2 text-sm text-slate-600">Visualização somente leitura criada em {formatDate(snapshot.share.created_at)}.</p>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <MetricCard label="Zonas" value={`${completedCount}/${snapshot.zones.total_count ?? zones.length}`} />
              <MetricCard label="Transporte" value={formatCount(snapshot.transport_points.length, "ponto", "pontos")} />
              <MetricCard label="Etapa" value={String(snapshot.journey.last_completed_step ?? 0)} />
            </div>
          </div>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-6xl gap-4 px-4 py-6 sm:px-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <aside className="h-fit rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-pastel-violet-600" />
            <h2 className="text-sm font-bold text-slate-900">Resumo</h2>
          </div>
          <dl className="mt-4 space-y-3 text-sm">
            <SummaryRow label="Estado" value={snapshot.journey.state} />
            <SummaryRow label="Zonas concluídas" value={`${completedCount} de ${snapshot.zones.total_count ?? zones.length}`} />
            <SummaryRow label="Pontos de transporte" value={String(snapshot.transport_points.length)} />
            <SummaryRow label="Atualizada em" value={formatDate(snapshot.journey.updated_at)} />
          </dl>
        </aside>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-900">Zonas da jornada</h2>
            <span className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
              {formatCount(zones.length, "zona", "zonas")}
            </span>
          </div>

          {zones.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
              Esta jornada ainda não possui zonas geradas.
            </div>
          ) : (
            <div className="grid gap-3">
              {zones.map((zone) => (
                <article key={zone.fingerprint} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Zona {compactFingerprint(zone.fingerprint)}</p>
                      <h3 className="mt-1 text-base font-bold text-slate-900">
                        {zone.travel_time_minutes != null ? `Até ${Math.round(zone.travel_time_minutes)} min` : "Tempo não informado"}
                      </h3>
                    </div>
                    <span className="w-fit rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600">
                      {zone.state === "complete" ? "Concluída" : "Em processamento"}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <MetricChip label="Preço mediano" value={formatCurrencyBr(zone.price_summary?.p50_price ?? null)} />
                    <MetricChip label="Imóveis ativos" value={String(zone.price_summary?.active_listing_count ?? 0)} />
                    <MetricChip label="POIs" value={String(Object.values(zone.poi_counts ?? {}).reduce((sum, count) => sum + count, 0))} />
                    <MetricChip label="Ocorrências" value={String(zone.safety_incidents_count ?? 0)} />
                  </div>
                </article>
              ))}
            </div>
          )}

          {snapshot.transport_points.length ? (
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <Train className="h-4 w-4 text-pastel-violet-600" />
                <h2 className="text-sm font-bold text-slate-900">Pontos de transporte considerados</h2>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {snapshot.transport_points.slice(0, 8).map((point) => (
                  <div key={point.id} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                    <p className="text-sm font-semibold text-slate-800">{point.name || "Ponto sem nome"}</p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {formatCount(point.route_count, "linha", "linhas")} · {Math.round(point.walk_distance_m)} m a pé
                    </p>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </section>
    </main>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-bold text-slate-900">{value}</p>
    </div>
  );
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-bold uppercase tracking-[0.1em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-semibold text-slate-800">{value}</dd>
    </div>
  );
}
