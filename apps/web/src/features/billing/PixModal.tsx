import { useEffect, useRef, useState } from "react";

import { ApiError, cancelPayment, createPixCheckout, getPaymentStatus, PixCheckoutResponse, PlanRead } from "../../api/client";

type PixModalProps = {
  plan: PlanRead;
  onClose: () => void;
  onSuccess: () => void;
};

type ModalState = "loading" | "pending" | "paid" | "expired" | "cancelled" | "error";

export function PixModal({ plan, onClose, onSuccess }: PixModalProps) {
  const [state, setState] = useState<ModalState>("loading");
  const [checkout, setCheckout] = useState<PixCheckoutResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    createPixCheckout(plan.slug)
      .then((data) => {
        if (cancelled) return;
        setCheckout(data);
        setState("pending");

        const expires = new Date(data.expires_at).getTime();
        timerRef.current = setInterval(() => {
          const left = Math.max(0, Math.floor((expires - Date.now()) / 1000));
          setTimeLeft(left);
          if (left === 0 && timerRef.current) {
            clearInterval(timerRef.current);
          }
        }, 1000);

        pollRef.current = setInterval(async () => {
          try {
            const status = await getPaymentStatus(data.payment_id);
            if (cancelled) return;

            if (status.status === "paid") {
              if (pollRef.current) clearInterval(pollRef.current);
              if (timerRef.current) clearInterval(timerRef.current);
              setState("paid");
              setTimeout(() => {
                onSuccess();
                onClose();
              }, 2000);
              return;
            }

            if (status.status === "expired" || status.status === "cancelled") {
              if (pollRef.current) clearInterval(pollRef.current);
              if (timerRef.current) clearInterval(timerRef.current);
              setState(status.status as ModalState);
            }
          } catch {
            // O polling continua. A próxima tentativa pode reconciliar o status no backend.
          }
        }, 5000);
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMsg(err instanceof ApiError ? err.message : "Erro ao gerar cobrança Pix.");
        setState("error");
      });

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [onClose, onSuccess, plan.slug]);

  const handleCopy = () => {
    if (!checkout) return;
    navigator.clipboard.writeText(checkout.pix_copy_paste).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  const handleCancel = async () => {
    if (!checkout) {
      onClose();
      return;
    }

    try {
      await cancelPayment(checkout.payment_id);
    } catch {
      // Mantém o fechamento do modal mesmo se o cancelamento remoto falhar.
    }
    onClose();
  };

  const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  const priceLabel = plan.price_brl ? `R$ ${Number(plan.price_brl).toFixed(2).replace(".", ",")}` : "Grátis";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-800">Pagar via Pix - {plan.name}</h2>
          <button onClick={handleCancel} className="text-xl leading-none text-slate-400 hover:text-slate-600">
            ×
          </button>
        </div>

        <div className="px-6 py-6">
          {state === "loading" && (
            <div className="flex flex-col items-center gap-4 py-8">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-violet-200 border-t-violet-600" />
              <p className="text-sm text-slate-500">Gerando cobrança Pix...</p>
            </div>
          )}

          {state === "pending" && checkout && (
            <div className="flex flex-col gap-5">
              <div className="rounded-xl bg-violet-50 p-4 text-center">
                <p className="text-2xl font-bold text-violet-700">{priceLabel}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {timeLeft !== null && timeLeft > 0 ? `Expira em ${formatTime(timeLeft)}` : "Cobrança gerada"}
                </p>
              </div>

              {checkout.qr_code_image_url && (
                <div className="flex justify-center">
                  <img src={checkout.qr_code_image_url} alt="QR Code Pix" className="h-48 w-48 rounded-lg border border-slate-200" />
                </div>
              )}

              <div>
                <p className="mb-1 text-xs font-medium text-slate-500">Pix Copia e Cola</p>
                <div className="flex gap-2">
                  <input
                    readOnly
                    value={checkout.pix_copy_paste}
                    className="flex-1 truncate rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-mono text-slate-700"
                  />
                  <button
                    onClick={handleCopy}
                    className="shrink-0 rounded-lg bg-violet-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-violet-700"
                  >
                    {copied ? "Copiado!" : "Copiar"}
                  </button>
                </div>
              </div>

              {checkout.ticket_url && (
                <a
                  href={checkout.ticket_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-center text-sm font-medium text-violet-700 transition-colors hover:bg-violet-100"
                >
                  Abrir cobrança no Mercado Pago
                </a>
              )}

              <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-4 py-3 text-xs text-amber-700">
                <span>⏳</span>
                <span>Aguardando confirmação do pagamento. A tela atualiza automaticamente.</span>
              </div>
            </div>
          )}

          {state === "paid" && (
            <div className="flex flex-col items-center gap-4 py-8 text-center">
              <div className="text-5xl">✅</div>
              <p className="text-lg font-semibold text-green-700">Pagamento confirmado!</p>
              <p className="text-sm text-slate-500">Seu plano {plan.name} está ativo. Redirecionando...</p>
            </div>
          )}

          {state === "expired" && (
            <div className="flex flex-col items-center gap-4 py-8 text-center">
              <div className="text-5xl">⌛</div>
              <p className="text-lg font-semibold text-slate-700">Cobrança expirada</p>
              <p className="text-sm text-slate-500">O prazo para pagamento venceu. Gere uma nova cobrança.</p>
              <button
                onClick={onClose}
                className="mt-2 rounded-lg bg-violet-600 px-6 py-2 text-sm font-semibold text-white hover:bg-violet-700"
              >
                Fechar
              </button>
            </div>
          )}

          {state === "cancelled" && (
            <div className="flex flex-col items-center gap-4 py-8 text-center">
              <div className="text-5xl">❌</div>
              <p className="text-lg font-semibold text-slate-700">Cobrança cancelada</p>
              <button
                onClick={onClose}
                className="mt-2 rounded-lg bg-slate-200 px-6 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-300"
              >
                Fechar
              </button>
            </div>
          )}

          {state === "error" && (
            <div className="flex flex-col items-center gap-4 py-8 text-center">
              <div className="text-5xl">⚠️</div>
              <p className="text-lg font-semibold text-red-700">Erro ao gerar cobrança</p>
              <p className="text-sm text-slate-500">{errorMsg}</p>
              <button
                onClick={onClose}
                className="mt-2 rounded-lg bg-slate-200 px-6 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-300"
              >
                Fechar
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
