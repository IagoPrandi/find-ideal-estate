import { z, ZodSchema } from "zod";
import {
  JobRead,
  JobReadSchema,
  JourneyRead,
  JourneyReadSchema,
  FinalizeResponse,
  FinalListingsJson,
  FinalListingsJsonSchema,
  FinalizeResponseSchema,
  ListingsCollection,
  ListingsCollectionSchema,
  ListingsScrapeResponse,
  ListingsScrapeResponseSchema,
  RunCreateResponse,
  RunCreateResponseSchema,
  RunStatusResponse,
  RunStatusResponseSchema,
  SimpleMessageResponse,
  SimpleMessageResponseSchema,
  TransportLayersResponse,
  TransportLayersResponseSchema,
  TransportPointRead,
  TransportPointReadSchema,
  TransportStopsResponse,
  TransportStopsResponseSchema,
  ZoneDetailResponse,
  ZoneDetailResponseSchema,
  ZonesCollection,
  ZonesCollectionSchema
} from "./schemas";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
};

export class ApiError extends Error {
  status: number;
  recoverable: boolean;

  constructor(message: string, status: number, recoverable: boolean) {
    super(message);
    this.status = status;
    this.recoverable = recoverable;
  }
}

async function requestJson<T>(path: string, schema: ZodSchema<T>, options: RequestOptions = {}): Promise<T> {
  const method = options.method || "GET";
  const url = `${API_BASE}${path}`;

  if (import.meta.env.DEV) {
    console.debug("[API →]", method, url, options.body ?? null);
  }

  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json"
    },
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : {};

  if (import.meta.env.DEV) {
    console.debug("[API ←]", response.status, method, url, data);
  }

  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : "Erro inesperado da API.";
    const recoverable = response.status >= 500 || response.status === 429 || response.status === 408;
    throw new ApiError(detail, response.status, recoverable);
  }

  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ApiError("Payload da API inválido para o contrato esperado.", 500, false);
  }

  return parsed.data;
}

export function apiActionHint(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.recoverable) {
      return `${error.message} Tente novamente em alguns segundos.`;
    }
    if (error.status === 404) {
      return `${error.message} Verifique se o run_id existe e se a etapa anterior foi concluída.`;
    }
    if (error.status === 400) {
      return `${error.message} Revise os dados enviados e refaça a ação.`;
    }
    return `${error.message} Corrija a configuração e tente novamente.`;
  }

  return "Falha de comunicação. Verifique API, rede e tente novamente.";
}

export async function createRun(payload: {
  reference_points: Array<{ name: string; lat: number; lon: number }>;
  params: Record<string, unknown>;
}): Promise<RunCreateResponse> {
  return (await requestJson("/runs", RunCreateResponseSchema, {
    method: "POST",
    body: payload
  })) as RunCreateResponse;
}

export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  return (await requestJson(`/runs/${runId}/status`, RunStatusResponseSchema)) as RunStatusResponse;
}

export async function getZones(runId: string): Promise<ZonesCollection> {
  return (await requestJson(`/runs/${runId}/zones`, ZonesCollectionSchema)) as ZonesCollection;
}

export async function getZoneDetail(runId: string, zoneUid: string): Promise<ZoneDetailResponse> {
  return (await requestJson(`/runs/${runId}/zones/${zoneUid}/detail`, ZoneDetailResponseSchema, {
    method: "POST"
  })) as ZoneDetailResponse;
}

export async function selectZones(runId: string, zoneUids: string[]): Promise<SimpleMessageResponse> {
  return (await requestJson(`/runs/${runId}/zones/select`, SimpleMessageResponseSchema, {
    method: "POST",
    body: { zone_uids: zoneUids }
  })) as SimpleMessageResponse;
}

export async function scrapeZoneListings(
  runId: string,
  zoneUid: string,
  streetFilter?: string
): Promise<ListingsScrapeResponse> {
  return (await requestJson(`/runs/${runId}/zones/${zoneUid}/listings`, ListingsScrapeResponseSchema, {
    method: "POST",
    body: streetFilter ? { street_filter: streetFilter } : {}
  })) as ListingsScrapeResponse;
}

export async function finalizeRun(runId: string): Promise<FinalizeResponse> {
  return (await requestJson(`/runs/${runId}/finalize`, FinalizeResponseSchema, {
    method: "POST"
  })) as FinalizeResponse;
}

export async function getFinalListings(runId: string): Promise<ListingsCollection> {
  return (await requestJson(`/runs/${runId}/final/listings`, ListingsCollectionSchema)) as ListingsCollection;
}

export async function getFinalListingsJson(runId: string): Promise<FinalListingsJson> {
  return (await requestJson(`/runs/${runId}/final/listings.json`, FinalListingsJsonSchema)) as FinalListingsJson;
}

export async function getTransportLayers(runId: string): Promise<TransportLayersResponse> {
  return (await requestJson(
    `/runs/${runId}/transport/routes`,
    TransportLayersResponseSchema
  )) as TransportLayersResponse;
}

export async function getTransportStops(
  lon: number,
  lat: number,
  radiusM = 2500,
  bbox?: { minLon: number; minLat: number; maxLon: number; maxLat: number }
): Promise<TransportStopsResponse> {
  const params = bbox
    ? `bbox=${encodeURIComponent(`${bbox.minLon},${bbox.minLat},${bbox.maxLon},${bbox.maxLat}`)}`
    : `lon=${encodeURIComponent(String(lon))}&lat=${encodeURIComponent(String(lat))}&radius_m=${encodeURIComponent(String(radiusM))}`;
  return (await requestJson(
    `/transport/stops?${params}`,
    TransportStopsResponseSchema
  )) as TransportStopsResponse;
}

export async function getZoneStreets(runId: string, zoneUid: string): Promise<{ zone_uid: string; streets: string[] }> {
  return (await requestJson(
    `/runs/${runId}/zones/${zoneUid}/streets`,
    z.object({ zone_uid: z.string(), streets: z.array(z.string()) })
  )) as { zone_uid: string; streets: string[] };
}

export async function createJourney(payload: {
  input_snapshot?: Record<string, unknown>;
  secondary_reference_label?: string;
  secondary_reference_point?: { lat: number; lon: number };
}): Promise<JourneyRead> {
  return (await requestJson("/journeys", JourneyReadSchema, {
    method: "POST",
    body: payload
  })) as JourneyRead;
}

export async function getJourneyTransportPoints(journeyId: string): Promise<TransportPointRead[]> {
  return (await requestJson(
    `/journeys/${journeyId}/transport-points`,
    z.array(TransportPointReadSchema)
  )) as TransportPointRead[];
}

export async function createZoneGenerationJob(journeyId: string): Promise<JobRead> {
  return (await requestJson("/jobs", JobReadSchema, {
    method: "POST",
    body: {
      journey_id: journeyId,
      job_type: "zone_generation"
    }
  })) as JobRead;
}

export { API_BASE };
