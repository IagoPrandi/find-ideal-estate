import { useState } from "react";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getAccountCredits, getAccountPlan, getPlans, PlanRead } from "../../api/client";
import { useAuth } from "../auth/AuthContext";
import { PixModal } from "./PixModal";

export function ContaPage({ onClose }: { onClose: () => void }) {
  const { authStatus } = useAuth();
  const isProprietario = authStatus.user?.role === "proprietario";
  const queryClient = useQueryClient();
  const [renewPlan, setRenewPlan] = useState<PlanRead | null>(null);

  const { data: activePlan, isLoading: loadingPlan } = useQuery({
    queryKey: ["account", "plan"],
    queryFn: getAccountPlan,
    enabled: authStatus.is_authenticated,
    retry: false,
  });

  const { data: credits, isLoading: loadingCredits } = useQuery({
    queryKey: ["account", "credits"],
    queryFn: getAccountCredits,
    enabled: authStatus.is_authenticated,
  });

  const { data: plans = [] } = useQuery({
    queryKey: ["billing", "plans"],
    queryFn: getPlans,
    staleTime: 5 * 60 * 1000,
  });

  if (!authStatus.is_authenticated) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
        <div className="rounded-2xl bg-white p-8 text-center shadow-2xl">
          <p className="text-slate-600">Faça login para ver sua conta.</p>
          <button onClick={onClose} className="mt-4 rounded-lg bg-slate-200 px-6 py-2 text-sm font-semibold text-slate-700">
            Fechar
          </button>
        </div>
      </div>
    );
  }

  const formatDate = (value: string | null | undefined) => {
    if (!value) return "—";
    return new Date(value).toLocaleDateString("pt-BR");
  };

  const daysUntilExpiry = () => {
    if (!activePlan?.ends_at) return null;
    return Math.floor((new Date(activePlan.ends_at).getTime() - Date.now()) / 86400000);
  };

  const expDays = daysUntilExpiry();
  const shouldShowRenewalCta = expDays !== null && expDays <= 7 && activePlan?.plan.is_paid;
  const currentPlanFull = plans.find((plan) => plan.slug === activePlan?.plan.slug);

  const handleRenew = () => {
    if (currentPlanFull) setRenewPlan(currentPlanFull);
  };

  const handleRenewSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ["account", "plan"] });
    queryClient.invalidateQueries({ queryKey: ["account", "credits"] });
    setRenewPlan(null);
  };

  const totalCredits = credits ? credits.total : 0;
  const quota = credits?.monthly_quota ?? 0;
  const usedPct = quota > 0 && credits ? Math.min(100, Math.round(((quota - credits.cycle) / quota) * 100)) : 0;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/50 p-4 pt-16">
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-8 py-5">
          <h1 className="text-2xl font-bold text-slate-800">Minha conta</h1>
          <button onClick={onClose} className="text-2xl leading-none text-slate-400 hover:text-slate-600">
            ×
          </button>
        </div>

        <div className="space-y-6 p-8">
          <div>
            <p className="text-sm text-slate-500">Conta</p>
            <p className="mt-0.5 font-semibold text-slate-800">{authStatus.user?.email}</p>
            {isProprietario && (
              <span className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
                ★ Proprietário
              </span>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Plano</p>
            {loadingPlan ? (
              <div className="h-6 w-32 animate-pulse rounded bg-slate-100" />
            ) : activePlan ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <span className="rounded-full bg-violet-100 px-3 py-1 text-sm font-bold text-violet-700">
                    {activePlan.plan.name}
                  </span>
                  <span className={`text-xs font-medium ${activePlan.status === "active" ? "text-green-600" : "text-slate-400"}`}>
                    {activePlan.status === "active" ? "Ativo" : activePlan.status}
                  </span>
                </div>
                {activePlan.ends_at && (
                  <p className="text-xs text-slate-500">
                    Válido até: <span className="font-medium text-slate-700">{formatDate(activePlan.ends_at)}</span>
                    {expDays !== null && expDays >= 0 && (
                      <span className={`ml-2 ${expDays <= 7 ? "font-semibold text-amber-600" : "text-slate-400"}`}>
                        {expDays === 0 ? "(expira hoje)" : `(${expDays} dias restantes)`}
                      </span>
                    )}
                  </p>
                )}
                {shouldShowRenewalCta && (
                  <button
                    onClick={handleRenew}
                    className="mt-2 self-start rounded-lg bg-amber-500 px-4 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-amber-600"
                  >
                    Renovar assinatura
                  </button>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Nenhum plano ativo encontrado.</p>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Créditos</p>
            {loadingCredits ? (
              <div className="h-6 w-24 animate-pulse rounded bg-slate-100" />
            ) : credits ? (
              <div className="space-y-3">
                <div className="flex items-end gap-2">
                  <span className="text-3xl font-extrabold text-violet-700">{totalCredits}</span>
                  {quota > 0 && <span className="mb-0.5 text-sm text-slate-400">/ {quota} cota mensal</span>}
                </div>
                {quota > 0 && (
                  <div className="h-2 w-full rounded-full bg-slate-100">
                    <div className="h-2 rounded-full bg-violet-500 transition-all" style={{ width: `${usedPct}%` }} />
                  </div>
                )}
                <div className="flex gap-4 text-xs text-slate-500">
                  <span>
                    Ciclo: <strong>{credits.cycle}</strong>
                  </span>
                  {credits.rollover > 0 && (
                    <span>
                      Rollover: <strong>{credits.rollover}</strong>
                    </span>
                  )}
                  {credits.legacy > 0 && (
                    <span>
                      Avulsos: <strong>{credits.legacy}</strong>
                    </span>
                  )}
                </div>
                {credits.cycle_ends_at && <p className="text-xs text-slate-400">Ciclo encerra em: {formatDate(credits.cycle_ends_at)}</p>}
              </div>
            ) : (
              <p className="text-sm text-slate-500">—</p>
            )}
          </div>
        </div>
      </div>

      {renewPlan && (
        <PixModal
          plan={renewPlan}
          onClose={() => setRenewPlan(null)}
          onSuccess={handleRenewSuccess}
        />
      )}
    </div>
  );
}
