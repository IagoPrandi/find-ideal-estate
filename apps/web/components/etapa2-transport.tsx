"use client";

import { useEffect, useState } from "react";
import { useSSEEvents } from "../hooks/useSSEEvents";

type TransportPointRead = {
  id: string;
  name: string | null;
  modal_types: string[];
  walk_distance_m: number;
  route_count: number;
};

export type Etapa2Props = {
  journeyId: string;
  onNext: (selectedTransportPointIds: string[]) => void;
};

export function Etapa2TransportSelection({ journeyId, onNext }: Etapa2Props) {
  const [transportPoints, setTransportPoints] = useState<TransportPointRead[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const { addListener } = useSSEEvents(jobId);

  const loadTransportPoints = async () => {
    const response = await fetch(`/api/journeys/${journeyId}/transport-points`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Falha ao carregar pontos de transporte");
    }

    const data = (await response.json()) as TransportPointRead[];
    setTransportPoints(data);
    return data;
  };

  useEffect(() => {
    let cancelled = false;

    const bootstrapTransportSearch = async () => {
      setIsLoading(true);
      setError(null);
      setProgressPercent(0);
      setProgressMessage("Buscando pontos de transporte proximos...");

      try {
        const existingPoints = await loadTransportPoints();
        if (cancelled) {
          return;
        }

        if (existingPoints.length > 0) {
          setProgressPercent(100);
          setProgressMessage("Pontos de transporte carregados.");
          return;
        }

        const response = await fetch("/api/jobs", {
          method: "POST",
          headers: {
            "content-type": "application/json",
          },
          body: JSON.stringify({
            journey_id: journeyId,
            job_type: "transport_search",
            current_stage: "transport_search",
          }),
        });

        if (!response.ok) {
          throw new Error("Falha ao iniciar a busca de transporte");
        }

        const job = (await response.json()) as { id: string; progress_percent?: number };
        if (cancelled) {
          return;
        }

        setJobId(job.id);
        setProgressPercent(job.progress_percent ?? 0);
        setProgressMessage("Busca de transporte enfileirada.");
      } catch (e) {
        const message = e instanceof Error ? e.message : "Erro desconhecido";
        if (!cancelled) {
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    bootstrapTransportSearch();

    return () => {
      cancelled = true;
    };
  }, [journeyId]);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    const unregisterProgress = addListener("job.stage.progress", (event) => {
      if (event.data.stage !== "transport_search") {
        return;
      }

      const nextPercent = Number(event.data.payload_json?.progress_percent ?? 0);
      setProgressPercent(Number.isFinite(nextPercent) ? nextPercent : 0);
      setProgressMessage(event.data.message ?? "Atualizando busca de transporte...");
      setIsLoading(true);
    });

    const unregisterStarted = addListener("job.started", (event) => {
      if (event.data.stage !== "transport_search") {
        return;
      }

      setProgressMessage(event.data.message ?? "Busca de transporte iniciada.");
      setIsLoading(true);
    });

    const unregisterCompleted = addListener("job.completed", async (event) => {
      if (event.data.stage !== "transport_search") {
        return;
      }

      setProgressPercent(100);
      setProgressMessage(event.data.message ?? "Busca concluida. Carregando resultados...");

      try {
        await loadTransportPoints();
        setError(null);
        setProgressMessage("Pontos de transporte prontos para selecao.");
      } catch (e) {
        const message = e instanceof Error ? e.message : "Erro desconhecido";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    });

    const unregisterFailed = addListener("job.failed", (event) => {
      if (event.data.stage !== "transport_search") {
        return;
      }

      setError(event.data.message ?? "Falha na busca de transporte");
      setProgressMessage(null);
      setIsLoading(false);
    });

    return () => {
      unregisterProgress();
      unregisterStarted();
      unregisterCompleted();
      unregisterFailed();
    };
  }, [addListener, jobId, journeyId]);

  const toggleSelection = (id: string) => {
    const newIds = new Set(selectedIds);
    if (newIds.has(id)) {
      newIds.delete(id);
    } else {
      newIds.add(id);
    }
    setSelectedIds(newIds);
  };

  const handleStart = () => {
    if (selectedIds.size > 0) {
      onNext(Array.from(selectedIds));
    }
  };

  return (
    <div className="etapa-panel">
      <div className="etapa-header">
        <p className="eyebrow">Fase 3 · M3.6</p>
        <h2>Etapa 2: Seleção de transporte</h2>
        <p className="panel-intro">Selecione um ou mais pontos de transporte para gerar zonas de isócrona.</p>
      </div>

      {isLoading && <p className="loading">Carregando pontos de transporte...</p>}
      {progressMessage && (
        <div className="progress-card" aria-live="polite">
          <div className="progress-copy">
            <strong>{progressMessage}</strong>
            <span>{progressPercent}% concluido</span>
          </div>
          <div className="progress-track" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100}>
            <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
      )}
      {error && <p className="error-message">{error}</p>}

      {!isLoading && transportPoints.length === 0 && (
        <p className="empty-state">Nenhum ponto de transporte encontrado.</p>
      )}

      {!isLoading && transportPoints.length > 0 && (
        <>
          <div className="transport-points-list">
            {transportPoints.map((point) => (
              <button
                key={point.id}
                type="button"
                className={`transport-point-card ${selectedIds.has(point.id) ? "selected" : ""}`}
                onClick={() => toggleSelection(point.id)}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(point.id)}
                  onChange={() => toggleSelection(point.id)}
                  className="transport-checkbox"
                />
                <div className="point-info">
                  <strong>{point.name ?? "Ponto de transporte"}</strong>
                  <p className="point-type">{point.modal_types.join(", ") || "modal indisponível"}</p>
                  <p className="point-distance">{point.walk_distance_m} m a pé</p>
                </div>
                {point.route_count !== undefined && (
                  <span className="routes-badge">{point.route_count} rotas</span>
                )}
              </button>
            ))}
          </div>

          <button
            type="button"
            className={`primary-button ${selectedIds.size === 0 ? "disabled" : ""}`}
            onClick={handleStart}
            disabled={selectedIds.size === 0}
          >
            {selectedIds.size === 0
              ? "Selecione um ponto para continuar"
              : `Gerar zonas (${selectedIds.size} selecionado${selectedIds.size > 1 ? "s" : ""})`}
          </button>
        </>
      )}

      <style jsx>{`
        .etapa-panel {
          display: grid;
          gap: 24px;
          padding: 28px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: var(--radius-xl);
        }

        .etapa-header {
          display: grid;
          gap: 12px;
        }

        .eyebrow {
          margin: 0;
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 700;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }

        h2 {
          margin: 0;
          font-family: var(--font-display), sans-serif;
          font-size: 1.8rem;
          font-weight: 700;
        }

        .panel-intro {
          margin: 0;
          color: var(--muted);
          font-size: 1rem;
          line-height: 1.5;
        }

        .loading,
        .error-message,
        .empty-state {
          padding: 16px;
          border-radius: var(--radius-md);
          text-align: center;
        }

        .progress-card {
          display: grid;
          gap: 12px;
          padding: 16px;
          border: 1px solid var(--line);
          border-radius: var(--radius-md);
          background: var(--accent-soft);
        }

        .progress-copy {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          color: var(--accent-strong);
        }

        .progress-copy strong,
        .progress-copy span {
          font-size: 0.95rem;
        }

        .progress-track {
          width: 100%;
          height: 10px;
          border-radius: 999px;
          overflow: hidden;
          background: color-mix(in srgb, var(--accent) 16%, white);
        }

        .progress-fill {
          height: 100%;
          border-radius: inherit;
          background: linear-gradient(90deg, var(--accent), var(--accent-strong));
          transition: width 200ms ease;
        }

        .error-message {
          background: rgba(159, 43, 34, 0.14);
          color: var(--danger);
        }

        .empty-state {
          color: var(--muted);
        }

        .transport-points-list {
          display: grid;
          gap: 12px;
        }

        .transport-point-card {
          display: grid;
          grid-template-columns: auto 1fr auto;
          align-items: center;
          gap: 16px;
          padding: 16px;
          border: 1px solid var(--line);
          border-radius: var(--radius-md);
          background: transparent;
          cursor: pointer;
          transition: all 200ms ease;
        }

        .transport-point-card:hover {
          border-color: var(--accent);
          background: var(--accent-soft);
        }

        .transport-point-card.selected {
          border-color: var(--accent-strong);
          background: var(--accent-soft);
        }

        .transport-checkbox {
          width: 20px;
          height: 20px;
          cursor: pointer;
        }

        .point-info {
          display: grid;
          gap: 4px;
        }

        .point-info strong {
          margin: 0;
          font-size: 1rem;
          font-weight: 600;
        }

        .point-type,
        .point-distance {
          margin: 0;
          font-size: 0.875rem;
          color: var(--muted);
        }

        .routes-badge {
          padding: 4px 12px;
          background: var(--accent-soft);
          color: var(--accent-strong);
          border-radius: var(--radius-sm);
          font-size: 0.875rem;
          font-weight: 600;
        }

        .primary-button {
          padding: 12px 24px;
          background: var(--accent);
          color: var(--panel);
          border: none;
          border-radius: var(--radius-md);
          font-weight: 600;
          cursor: pointer;
          transition: background 200ms ease;
        }

        .primary-button:hover:not(.disabled) {
          background: var(--accent-strong);
        }

        .primary-button.disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}
