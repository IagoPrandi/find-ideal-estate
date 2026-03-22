"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type JobEvent = {
  event: string;
  data: Record<string, any>;
  id?: string;
  timestamp?: string;
};

type EventListener = (event: JobEvent) => void;

export function useSSEEvents(jobId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const eRef = useRef<EventSource | null>(null);
  const listenersRef = useRef<Map<string, Set<EventListener>>>(new Map());

  const addListener = useCallback((eventType: string, handler: EventListener) => {
    if (!listenersRef.current.has(eventType)) {
      listenersRef.current.set(eventType, new Set());
    }
    listenersRef.current.get(eventType)!.add(handler);

    return () => {
      listenersRef.current.get(eventType)?.delete(handler);
    };
  }, []);

  useEffect(() => {
    if (!jobId) {
      if (eRef.current) {
        eRef.current.close();
        eRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    // Close any existing connection
    if (eRef.current) {
      eRef.current.close();
    }

    const url = `/api/jobs/${jobId}/events`;
    const eventSource = new EventSource(url);

    eventSource.addEventListener("message", (event) => {
      try {
        const parsed = JSON.parse(event.data);
        const eventType = parsed.event_type || event.type;
        const jobEvent: JobEvent = {
          event: eventType,
          data: parsed,
          id: event.lastEventId,
          timestamp: new Date().toISOString(),
        };

        setEvents((prev) => [...prev, jobEvent]);

        // Notify listeners
        const listeners = listenersRef.current.get(eventType);
        if (listeners) {
          listeners.forEach((handler) => handler(jobEvent));
        }
      } catch (e) {
        console.error("Failed to parse SSE event:", e);
      }
    });

    eventSource.addEventListener("job.created", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.created", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.created")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("job.started", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.started", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.started")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("job.progress", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.progress", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.progress")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("job.stage.progress", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.stage.progress", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.stage.progress")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("job.partial_result.ready", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.partial_result.ready", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.partial_result.ready")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("job.completed", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.completed", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.completed")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("job.failed", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "job.failed", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("job.failed")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("zone.generated", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "zone.generated", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("zone.generated")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("zone.badges.updated", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "zone.badges.updated", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("zone.badges.updated")?.forEach((h) => h(jobEvent));
    });

    eventSource.addEventListener("zones.badges.finalized", (event) => {
      const data = JSON.parse(event.data);
      const jobEvent: JobEvent = { event: "zones.badges.finalized", data };
      setEvents((prev) => [...prev, jobEvent]);
      listenersRef.current.get("zones.badges.finalized")?.forEach((h) => h(jobEvent));
    });

    eventSource.onerror = () => {
      setError("SSE connection failed");
      setIsConnected(false);
      eventSource.close();
    };

    setIsConnected(true);
    setError(null);
    eRef.current = eventSource;

    return () => {
      if (eRef.current) {
        eRef.current.close();
        eRef.current = null;
      }
      setIsConnected(false);
    };
  }, [jobId]);

  return {
    isConnected,
    events,
    error,
    addListener,
  };
}
