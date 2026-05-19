import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import {
  addAdminScrapingQueueAddresses,
  AdminScrapingBatch,
  ApiError,
  cancelAdminScrapingBatch,
  getAdminScrapingBatches,
  getAdminScrapingOverview,
  getAdminScrapingQueue,
  getAdminUsers,
  removeAdminScrapingQueueAddress,
  runAdminScrapingNow,
  updateAdminUserRole,
} from "../../api/client";
import { useAuth } from "../auth/AuthContext";

type AdminTab = "overview" | "queue" | "batches" | "users";

const ACTIVE_STATES = new Set(["pending", "running", "retrying"]);

function toMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Não foi possível concluir a ação administrativa.";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
}

function formatRemaining(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours}h ${rest}min`;
}

function statusLabel(status: string | null | undefined): string {
  const labels: Record<string, string> = {
    pending: "Pendente",
    running: "Em execução",
    retrying: "Tentando novamente",
    completed: "Concluída",
    failed: "Falhou",
    cancelled: "Cancelada",
    cancelled_partial: "Cancelada parcialmente",
    success: "Sucesso",
    partial: "Parcial",
    success_empty: "Sem endereços",
  };
  return status ? labels[status] ?? status : "—";
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-extrabold tracking-tight text-slate-900">{value}</p>
    </div>
  );
}

function BatchTargetRows({ batch }: { batch: AdminScrapingBatch }) {
  const targets = Object.entries(batch.target_statuses || {});
  if (!targets.length) {
    return <p className="text-sm text-slate-500">Esta batelada ainda não registrou status por endereço.</p>;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full min-w-[48rem] text-left text-sm">
        <thead className="bg-slate-50 text-[11px] uppercase tracking-[0.12em] text-slate-500">
          <tr>
            <th className="px-3 py-2">Endereço</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Imóveis</th>
            <th className="px-3 py-2">Tempo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {targets.map(([key, raw]) => {
            const item = raw as Record<string, unknown>;
            return (
              <tr key={key}>
                <td className="px-3 py-2">
                  <p className="font-medium text-slate-800">{String(item.search_location_label || item.search_location_normalized || key)}</p>
                  <p className="text-xs text-slate-400">{String(item.search_type || "rent")} · {String(item.usage_type || "residential")}</p>
                </td>
                <td className="px-3 py-2 text-slate-700">{statusLabel(String(item.status || ""))}</td>
                <td className="px-3 py-2 text-slate-700">{typeof item.total_count === "number" ? item.total_count : "—"}</td>
                <td className="px-3 py-2 text-slate-700">{formatDurationMs(typeof item.duration_ms === "number" ? item.duration_ms : null)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ScrapingAdminPage() {
  const { authStatus, isLoading } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");
  const [addressesText, setAddressesText] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const isDeveloper = Boolean(authStatus.user?.is_superuser);
  const queriesEnabled = authStatus.is_authenticated && isDeveloper;

  const overviewQuery = useQuery({
    queryKey: ["admin", "scraping", "overview"],
    queryFn: getAdminScrapingOverview,
    enabled: queriesEnabled,
    refetchInterval: 10000,
  });

  const queueQuery = useQuery({
    queryKey: ["admin", "scraping", "queue"],
    queryFn: getAdminScrapingQueue,
    enabled: queriesEnabled,
  });

  const batchesQuery = useQuery({
    queryKey: ["admin", "scraping", "batches"],
    queryFn: getAdminScrapingBatches,
    enabled: queriesEnabled,
    refetchInterval: 10000,
  });

  const usersQuery = useQuery({
    queryKey: ["admin", "users", userSearch],
    queryFn: () => getAdminUsers(userSearch),
    enabled: queriesEnabled,
  });

  const refreshAdminData = () => {
    void queryClient.invalidateQueries({ queryKey: ["admin", "scraping"] });
    void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  };

  const runNowMutation = useMutation({
    mutationFn: runAdminScrapingNow,
    onSuccess: (data) => {
      setNotice(`Batelada criada com ${data.target_count} endereço(s).`);
      setExpandedBatchId(data.job.id);
      refreshAdminData();
    },
    onError: (error) => setNotice(toMessage(error)),
  });

  const addQueueMutation = useMutation({
    mutationFn: () => addAdminScrapingQueueAddresses({
      addresses: addressesText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    }),
    onSuccess: (data) => {
      setNotice(`${data.affected_count} endereço(s) adicionados à próxima batelada.`);
      setAddressesText("");
      refreshAdminData();
    },
    onError: (error) => setNotice(toMessage(error)),
  });

  const removeQueueMutation = useMutation({
    mutationFn: removeAdminScrapingQueueAddress,
    onSuccess: (data) => {
      setNotice(`${data.affected_count} registro(s) removidos da fila.`);
      refreshAdminData();
    },
    onError: (error) => setNotice(toMessage(error)),
  });

  const cancelBatchMutation = useMutation({
    mutationFn: cancelAdminScrapingBatch,
    onSuccess: () => {
      setNotice("Cancelamento solicitado.");
      refreshAdminData();
    },
    onError: (error) => setNotice(toMessage(error)),
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "user" | "proprietario" }) => updateAdminUserRole(userId, role),
    onSuccess: () => {
      setNotice("Função atualizada.");
      refreshAdminData();
    },
    onError: (error) => setNotice(toMessage(error)),
  });

  const activeJob = overviewQuery.data?.active_job || null;
  const hasActiveBatch = Boolean(activeJob && ACTIVE_STATES.has(activeJob.state));
  const runNowDisabled = hasActiveBatch || runNowMutation.isPending || (queueQuery.data?.total_count ?? 0) === 0;

  const selectedBatch = useMemo(
    () => batchesQuery.data?.items.find((batch) => batch.job.id === expandedBatchId) || null,
    [batchesQuery.data?.items, expandedBatchId],
  );

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 text-slate-600">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Verificando acesso
      </main>
    );
  }

  if (!queriesEnabled) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
        <div className="max-w-md rounded-lg border border-amber-200 bg-white p-6 text-center shadow-lg">
          <AlertTriangle className="mx-auto h-8 w-8 text-amber-500" />
          <h1 className="mt-3 text-xl font-bold text-slate-900">Acesso restrito</h1>
          <p className="mt-2 text-sm text-slate-600">Esta página é exclusiva para o desenvolvedor.</p>
          <button
            type="button"
            onClick={() => { window.location.hash = ""; }}
            className="mt-5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
          >
            Voltar ao mapa
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-6">
        <header className="flex flex-col justify-between gap-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-center">
          <div>
            <button
              type="button"
              onClick={() => { window.location.hash = ""; }}
              className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
            >
              <ArrowLeft className="h-4 w-4" />
              Voltar ao mapa
            </button>
            <h1 className="text-2xl font-extrabold tracking-tight">Painel de scraping</h1>
            <p className="mt-1 text-sm text-slate-500">Fila, bateladas e permissões operacionais.</p>
          </div>
          <button
            type="button"
            onClick={refreshAdminData}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
        </header>

        {notice ? (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
            <span>{notice}</span>
            <button type="button" aria-label="Fechar aviso" onClick={() => setNotice(null)}>
              <XCircle className="h-4 w-4 text-slate-400" />
            </button>
          </div>
        ) : null}

        <nav className="flex flex-wrap gap-2">
          {[
            ["overview", "Visão geral"],
            ["queue", "Fila"],
            ["batches", "Bateladas"],
            ["users", "Usuários"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key as AdminTab)}
              className={`rounded-lg px-4 py-2 text-sm font-bold transition ${
                activeTab === key ? "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        {activeTab === "overview" ? (
          <section className="grid gap-5 lg:grid-cols-[1fr_22rem]">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard label="Endereços na fila" value={overviewQuery.data?.queue_count ?? "—"} />
              <MetricCard label="Próximo scraping" value={formatDateTime(overviewQuery.data?.next_run_at)} />
              <MetricCard label="Tempo restante" value={formatRemaining(overviewQuery.data?.seconds_until_next_run)} />
              <MetricCard label="Última batelada" value={statusLabel(overviewQuery.data?.latest_job?.state)} />
            </div>
            <aside className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-400">Controle imediato</p>
              <button
                type="button"
                disabled={runNowDisabled}
                onClick={() => runNowMutation.mutate()}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-3 text-sm font-extrabold text-white shadow-sm transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {runNowMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Executar agora
              </button>
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                {hasActiveBatch
                  ? `Batelada ${activeJob?.id.slice(0, 8)} em ${statusLabel(activeJob?.state).toLowerCase()}.`
                  : "Inicia uma batelada com os endereços elegíveis da fila atual."}
              </p>
              {activeJob ? (
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab("batches");
                    setExpandedBatchId(activeJob.id);
                  }}
                  className="mt-4 text-sm font-semibold text-violet-700 hover:text-violet-900"
                >
                  Ver batelada ativa
                </button>
              ) : null}
            </aside>
          </section>
        ) : null}

        {activeTab === "queue" ? (
          <section className="grid gap-5 lg:grid-cols-[22rem_1fr]">
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-bold">Adicionar endereços</h2>
              <p className="mt-1 text-sm text-slate-500">Um endereço por linha.</p>
              <textarea
                value={addressesText}
                onChange={(event) => setAddressesText(event.target.value)}
                className="mt-4 h-44 w-full resize-none rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm outline-none focus:border-violet-400 focus:bg-white"
                placeholder="Rua Botucatu, Vila Mariana, São Paulo"
              />
              <button
                type="button"
                disabled={addQueueMutation.isPending || !addressesText.trim()}
                onClick={() => addQueueMutation.mutate()}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {addQueueMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Adicionar à fila
              </button>
            </div>
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                <h2 className="font-bold">Próxima batelada</h2>
                <span className="text-sm text-slate-500">{queueQuery.data?.total_count ?? 0} endereço(s)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[54rem] text-left text-sm">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Endereço</th>
                      <th className="px-3 py-2">Demanda</th>
                      <th className="px-3 py-2">Cache</th>
                      <th className="px-3 py-2">Última atualização</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(queueQuery.data?.items || []).map((item) => (
                      <tr key={`${item.search_type}:${item.usage_type}:${item.search_location_normalized}`}>
                        <td className="px-3 py-2">
                          <p className="font-medium text-slate-800">{item.search_location_label}</p>
                          <p className="text-xs text-slate-400">{item.search_location_normalized}</p>
                        </td>
                        <td className="px-3 py-2 text-slate-700">{item.demand_count}</td>
                        <td className="px-3 py-2 text-slate-700">{statusLabel(item.cache_status)}</td>
                        <td className="px-3 py-2 text-slate-700">{formatDateTime(item.last_prewarmed_at || item.scraped_at)}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            aria-label={`Remover ${item.search_location_label}`}
                            disabled={removeQueueMutation.isPending}
                            onClick={() => removeQueueMutation.mutate(item.search_location_normalized)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:border-rose-200 hover:text-rose-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "batches" ? (
          <section className="grid gap-5">
            {(batchesQuery.data?.items || []).map((batch) => {
              const isExpanded = expandedBatchId === batch.job.id;
              const canCancel = ACTIVE_STATES.has(batch.job.state);
              return (
                <div key={batch.job.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
                    <button
                      type="button"
                      onClick={() => setExpandedBatchId(isExpanded ? null : batch.job.id)}
                      className="text-left"
                    >
                      <p className="font-mono text-xs text-slate-400">{batch.job.id}</p>
                      <p className="mt-1 font-bold text-slate-900">
                        {statusLabel(batch.status || batch.job.state)} · {batch.target_count} endereço(s)
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        {formatDateTime(batch.job.created_at)} · {formatDurationMs(batch.duration_ms)}
                      </p>
                    </button>
                    {canCancel ? (
                      <button
                        type="button"
                        disabled={cancelBatchMutation.isPending}
                        onClick={() => cancelBatchMutation.mutate(batch.job.id)}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50"
                      >
                        <XCircle className="h-4 w-4" />
                        Cancelar
                      </button>
                    ) : null}
                  </div>
                  {isExpanded ? (
                    <div className="mt-4 overflow-x-auto">
                      <BatchTargetRows batch={selectedBatch || batch} />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </section>
        ) : null}

        {activeTab === "users" ? (
          <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-col justify-between gap-3 border-b border-slate-200 px-4 py-3 md:flex-row md:items-center">
              <div className="flex items-center gap-2">
                <Users className="h-5 w-5 text-slate-500" />
                <h2 className="font-bold">Usuários</h2>
              </div>
              <input
                value={userSearch}
                onChange={(event) => setUserSearch(event.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-violet-400 md:w-80"
                placeholder="Buscar por e-mail ou nome"
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[48rem] text-left text-sm">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Usuário</th>
                    <th className="px-3 py-2">Criado em</th>
                    <th className="px-3 py-2">Função</th>
                    <th className="px-3 py-2">Acesso</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(usersQuery.data?.items || []).map((user) => (
                    <tr key={user.id}>
                      <td className="px-3 py-2">
                        <p className="font-medium text-slate-800">{user.display_name || "Sem nome"}</p>
                        <p className="text-xs text-slate-400">{user.email}</p>
                      </td>
                      <td className="px-3 py-2 text-slate-700">{formatDateTime(user.created_at)}</td>
                      <td className="px-3 py-2">
                        <select
                          value={user.role}
                          disabled={updateRoleMutation.isPending}
                          onChange={(event) => updateRoleMutation.mutate({
                            userId: user.id,
                            role: event.target.value as "user" | "proprietario",
                          })}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
                        >
                          <option value="user">Usuário</option>
                          <option value="proprietario">Proprietário</option>
                        </select>
                      </td>
                      <td className="px-3 py-2 text-slate-700">
                        {user.is_superuser ? "Desenvolvedor" : user.is_active ? "Ativo" : "Inativo"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {overviewQuery.error || queueQuery.error || batchesQuery.error || usersQuery.error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
            {toMessage(overviewQuery.error || queueQuery.error || batchesQuery.error || usersQuery.error)}
          </div>
        ) : null}
      </div>
    </main>
  );
}
