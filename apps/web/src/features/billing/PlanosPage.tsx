import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { activateProprietarioPlan, getPlans, getAccountPlan, PlanRead } from "../../api/client";
import { useAuth } from "../auth/AuthContext";
import { PixModal } from "./PixModal";

const PLAN_FEATURES: Record<string, string[]> = {
  anonymous: ["300 créditos de sessão", "Sem favoritos", "Parâmetros travados"],
  free: ["350 créditos/mês", "5 imóveis salvos", "2 zonas salvas", "Retenção 7 dias"],
  basico: ["800 créditos/mês", "20 imóveis salvos", "4 zonas salvas", "Retenção 30 dias", "Parametrização limitada", "4 métricas"],
  pro: ["4.000 créditos/mês", "100 imóveis salvos", "20 zonas salvas", "Retenção 30 dias", "Parametrização completa", "Métricas ilimitadas"],
  pro_max: ["20.000 créditos/mês", "100 imóveis salvos", "20 zonas salvas", "Retenção 30 dias", "Parametrização completa", "Métricas ilimitadas"],
};

export function PlanosPage({ onClose }: { onClose: () => void }) {
  const { authStatus, openAuthModal } = useAuth();
  const queryClient = useQueryClient();
  const [selectedPlan, setSelectedPlan] = useState<PlanRead | null>(null);
  const [activating, setActivating] = useState<string | null>(null);

  const isProprietario = authStatus.user?.role === "proprietario";

  const { data: plans = [] } = useQuery({
    queryKey: ["billing", "plans"],
    queryFn: getPlans,
    staleTime: 5 * 60 * 1000,
  });

  const { data: activePlan } = useQuery({
    queryKey: ["account", "plan"],
    queryFn: getAccountPlan,
    enabled: authStatus.is_authenticated,
    retry: false,
  });

  const handlePlanClick = async (plan: PlanRead) => {
    if (!authStatus.is_authenticated) {
      openAuthModal("register");
      return;
    }
    if (isProprietario) {
      if (activating) return;
      setActivating(plan.slug);
      try {
        await activateProprietarioPlan(plan.slug);
        queryClient.invalidateQueries({ queryKey: ["account", "plan"] });
        queryClient.invalidateQueries({ queryKey: ["account", "credits"] });
      } finally {
        setActivating(null);
      }
      return;
    }
    if (!plan.is_paid) return;
    setSelectedPlan(plan);
  };

  const handlePixSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ["account", "plan"] });
    queryClient.invalidateQueries({ queryKey: ["account", "credits"] });
    setSelectedPlan(null);
    onClose();
  };

  const formatPrice = (plan: PlanRead) => {
    if (!plan.is_paid) return plan.slug === "free" ? "Grátis" : "—";
    if (!plan.price_brl) return "—";
    return `R$ ${Number(plan.price_brl).toFixed(2).replace(".", ",")}`;
  };

  const isCurrentPlan = (plan: PlanRead) => activePlan?.plan.slug === plan.slug;

  const visiblePlans = plans.filter((p) => p.slug !== "anonymous");

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/50 p-4 pt-16">
      <div className="w-full max-w-5xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-8 py-5">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Planos</h1>
            <p className="text-sm text-slate-500 mt-0.5">Escolha o plano ideal para sua busca imobiliária</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">×</button>
        </div>

        <div className="grid grid-cols-1 gap-6 p-8 sm:grid-cols-2 lg:grid-cols-4">
          {visiblePlans.map((plan) => {
            const isCurrent = isCurrentPlan(plan);
            const isHighlighted = plan.slug === "pro";
            return (
              <div
                key={plan.id}
                className={`relative flex flex-col rounded-2xl border-2 p-6 transition-all ${
                  isHighlighted
                    ? "border-violet-500 shadow-lg shadow-violet-100"
                    : isCurrent
                    ? "border-green-400"
                    : "border-slate-200 hover:border-violet-300"
                }`}
              >
                {isHighlighted && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-violet-600 px-3 py-0.5 text-xs font-semibold text-white">
                    Popular
                  </span>
                )}
                {isCurrent && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-green-500 px-3 py-0.5 text-xs font-semibold text-white">
                    Plano atual
                  </span>
                )}

                <h3 className="text-lg font-bold text-slate-800">{plan.name}</h3>
                <p className={`mt-1 text-2xl font-extrabold ${isHighlighted ? "text-violet-700" : "text-slate-700"}`}>
                  {formatPrice(plan)}
                  {plan.is_paid && <span className="text-sm font-normal text-slate-400">/mês</span>}
                </p>

                <ul className="mt-4 flex-1 space-y-2">
                  {(PLAN_FEATURES[plan.slug] ?? []).map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
                      <span className="mt-0.5 text-violet-500">✓</span>
                      {f}
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => void handlePlanClick(plan)}
                  disabled={isCurrent || (!isProprietario && !plan.is_paid) || activating === plan.slug}
                  className={`mt-6 w-full rounded-xl py-2.5 text-sm font-semibold transition-colors ${
                    isCurrent
                      ? "bg-green-100 text-green-700 cursor-default"
                      : isProprietario
                      ? "bg-amber-500 text-white hover:bg-amber-600"
                      : !plan.is_paid
                      ? "bg-slate-100 text-slate-400 cursor-default"
                      : isHighlighted
                      ? "bg-violet-600 text-white hover:bg-violet-700"
                      : "bg-slate-800 text-white hover:bg-slate-900"
                  }`}
                >
                  {isCurrent
                    ? "Plano ativo"
                    : activating === plan.slug
                    ? "Ativando..."
                    : isProprietario
                    ? "Ativar grátis"
                    : !plan.is_paid
                    ? "Incluído"
                    : "Assinar via Pix"}
                </button>
              </div>
            );
          })}
        </div>

        <div className="border-t border-slate-100 px-8 py-4">
          {isProprietario ? (
            <p className="text-xs text-amber-600 text-center font-medium">
              Acesso proprietário ativo — troca de plano sem pagamento.
            </p>
          ) : (
            <p className="text-xs text-slate-400 text-center">
              Pagamento via Pix com QR Code ou Pix Copia e Cola. Ativação em até 1 hora após confirmação.
            </p>
          )}
        </div>
      </div>

      {selectedPlan && (
        <PixModal
          plan={selectedPlan}
          onClose={() => setSelectedPlan(null)}
          onSuccess={handlePixSuccess}
        />
      )}
    </div>
  );
}
