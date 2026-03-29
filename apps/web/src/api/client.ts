import { z, ZodSchema } from "zod";
import {
  FinalListingsJson,
  FinalizeResponse,
  JobRead,
  JobReadSchema,
  JourneyRead,
  JourneyReadSchema,
  ListingsCollection,
  ListingsScrapeResponse,
  PriceRollupRead,
  PriceRollupReadSchema,
  RunCreateResponse,
  RunStatusResponse,
  SimpleMessageResponse,
  TransportBusDetailResponse,
  TransportBusDetailResponseSchema,
  TransportLayersResponse,
  TransportLayersResponseSchema,
  TransportPointRead,
  TransportPointReadSchema,
  TransportStopsResponse,
  TransportStopsResponseSchema,
  ZoneDetailResponse,
  ZonesCollection,
  ZonesCollectionSchema,
  JourneyZonesListResponseSchema,
  SearchAddressSuggestionBackendSchema,
  ListingCardReadBackendSchema,
  ListingsRequestResultBackendSchema
} from "./schemas";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

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

function legacyRunNotSupported(action: string): never {
  throw new ApiError(
    `${action} usa contrato legado de run e ainda nao foi migrado para journey/jobs nesta tela.`,
    501,
    false
  );
}

async function requestJson<T>(path: string, schema: ZodSchema<T>, options: RequestOptions = {}): Promise<T> {
  const method = options.method || "GET";
  const url = `${API_BASE}${path}`;

  if (import.meta.env.DEV) {
    console.debug("[API →]", method, url, options.body ?? null);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json"
      },
      body: options.body ? JSON.stringify(options.body) : undefined
    });
  } catch {
    throw new ApiError(
      "Nao foi possivel conectar com a API. Verifique se o backend esta ativo e se CORS/rede estao configurados.",
      0,
      true
    );
  }

  const text = await response.text();
  let data: unknown = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(
        "A API respondeu com payload invalido (esperado JSON).",
        response.status || 500,
        false
      );
    }
  }

  if (import.meta.env.DEV) {
    console.debug("[API ←]", response.status, method, url, data);
  }

  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data && typeof (data as { detail?: unknown }).detail === "string"
        ? ((data as { detail: string }).detail)
        : "Erro inesperado da API.";
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
      return `${error.message} Verifique se o recurso existe e se a etapa anterior foi concluída.`;
    }
    if (error.status === 400) {
      return `${error.message} Revise os dados enviados e refaça a ação.`;
    }
    return `${error.message} Corrija a configuração e tente novamente.`;
  }

  return "Falha de comunicação. Verifique API, rede e tente novamente.";
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

function computeGeoJsonCentroid(geom: any): { lon: number; lat: number } | null {
  // Aproximação simples: média de vértices para colocar elementos no mapa.
  if (!geom || typeof geom !== "object") return null;

  const points: Array<[number, number]> = [];

  const collect = (g: any) => {
    if (!g || typeof g !== "object") return;
    if (g.type === "Polygon") {
      const ring = g.coordinates?.[0];
      if (!Array.isArray(ring)) return;
      for (const p of ring) {
        if (Array.isArray(p) && p.length >= 2) points.push([Number(p[0]), Number(p[1])]);
      }
      return;
    }
    if (g.type === "MultiPolygon") {
      const polys = g.coordinates;
      if (!Array.isArray(polys)) return;
      for (const poly of polys) collect({ type: "Polygon", coordinates: poly });
    }
  };

  collect(geom);
  const valid = points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (!valid.length) return null;

  const sum = valid.reduce(
    (acc, [lon, lat]) => ({ lon: acc.lon + lon, lat: acc.lat + lat }),
    { lon: 0, lat: 0 }
  );

  return { lon: sum.lon / valid.length, lat: sum.lat / valid.length };
}

export async function getJourneyZonesCollection(journeyId: string): Promise<ZonesCollection> {
  const backend = await requestJson(`/journeys/${journeyId}/zones`, JourneyZonesListResponseSchema);

  const fc = {
    type: "FeatureCollection" as const,
    features: backend.zones.map((zj) => {
      const geometryRaw = (zj.isochrone_geom || {}) as Record<string, unknown>;
      const geometry = {
        ...geometryRaw,
        type: typeof geometryRaw.type === "string" ? geometryRaw.type : "Polygon",
        coordinates: geometryRaw.coordinates ?? []
      };
      const centroid = computeGeoJsonCentroid(zj.isochrone_geom);
      return {
        type: "Feature" as const,
        geometry,
        properties: {
          zone_uid: zj.fingerprint,
          centroid_lon: centroid?.lon,
          centroid_lat: centroid?.lat,
          time_agg: zj.travel_time_minutes ?? undefined,
          green_area_ratio: zj.green_area_m2 ?? undefined,
          flood_area_ratio: zj.flood_area_m2 ?? undefined,
          poi_counts: zj.poi_counts ?? undefined,
          badges_provisional: zj.badges_provisional ?? undefined
        }
      };
    })
  };

  return ZonesCollectionSchema.parse(fc) as ZonesCollection;
}

export type SearchAddressSuggestion = z.output<typeof SearchAddressSuggestionBackendSchema>;
export async function getZoneAddressSuggestions(
  journeyId: string,
  zoneFingerprint: string,
  q: string
): Promise<SearchAddressSuggestion[]> {
  return await requestJson(
    `/journeys/${journeyId}/listings/address-suggest?zone_fingerprint=${encodeURIComponent(zoneFingerprint)}&q=${encodeURIComponent(q)}`,
    z.array(SearchAddressSuggestionBackendSchema)
  );
}

export type ListingsScrapePlanResponse = z.output<typeof ListingsScrapePlanResponseSchema>;
export async function getListingsScrapePlan(
  journeyId: string,
  searchType: string,
  usageType: string = "residential"
): Promise<ListingsScrapePlanResponse> {
  return await requestJson(
    `/journeys/${journeyId}/listings/scrape-plan?search_type=${encodeURIComponent(searchType)}&usage_type=${encodeURIComponent(usageType)}`,
    ListingsScrapePlanResponseSchema
  );
}

export type ListingCardRead = z.output<typeof ListingCardReadBackendSchema>;
export type ListingsRequestResult = z.output<typeof ListingsRequestResultBackendSchema>;
export async function searchZoneListings(
  journeyId: string,
  zoneFingerprint: string,
  payload: {
    search_location_normalized: string;
    search_location_label: string;
    search_location_type: string;
    search_type: string;
    usage_type?: string;
  }
): Promise<ListingsRequestResult> {
  return (await requestJson(
    `/journeys/${journeyId}/listings/search`,
    ListingsRequestResultBackendSchema,
    {
      method: "POST",
      body: {
        zone_fingerprint: zoneFingerprint,
        ...payload
      }
    }
  )) as ListingsRequestResult;
}

// Compat layer while legacy run-based UI flow is being migrated to journey/jobs.
export async function createRun(payload: {
  reference_points: Array<{ name: string; lat: number; lon: number }>;
  params: Record<string, unknown>;
}): Promise<RunCreateResponse> {
  const first = payload.reference_points[0];
  if (!first) {
    throw new ApiError("reference_points vazio", 400, false);
  }

  const journey = await createJourney({
    input_snapshot: {
      reference_point: { lat: first.lat, lon: first.lon },
      ...payload.params
    }
  });

  return {
    run_id: journey.id,
    status: {
      state: journey.state,
      stage: "journey_created"
    }
  };
}

export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  const journey = await requestJson(`/journeys/${runId}`, JourneyReadSchema);
  return {
    run_id: runId,
    status: {
      state: String(journey.state || "running"),
      stage: "journey"
    }
  };
}

export async function getZones(runId: string): Promise<ZonesCollection> {
  return getJourneyZonesCollection(runId);
}

export async function getZoneDetail(runId: string, zoneUid: string): Promise<ZoneDetailResponse> {
  const zones = await requestJson(`/journeys/${runId}/zones`, JourneyZonesListResponseSchema);
  const zone = zones.zones.find((item) => item.fingerprint === zoneUid);
  if (!zone) {
    throw new ApiError("Zona nao encontrada na jornada atual.", 404, false);
  }

  return {
    zone_uid: zoneUid,
    zone_name: `Zona ${zoneUid.slice(0, 8)}`,
    green_area_ratio: Number(zone.green_area_m2 || 0),
    flood_area_ratio: Number(zone.flood_area_m2 || 0),
    poi_count_by_category: zone.poi_counts || {},
    bus_lines_count: 0,
    train_lines_count: 0,
    bus_stop_count: 0,
    train_station_count: 0,
    lines_used_for_generation: [],
    transport_points: [],
    poi_points: [],
    streets_count: 0,
    has_street_data: false,
    has_poi_data: Boolean(zone.poi_counts && Object.keys(zone.poi_counts).length > 0),
    has_transport_data: false,
    public_safety: null
  };
}

export async function selectZones(_runId: string, _zoneUids: string[]): Promise<SimpleMessageResponse> {
  legacyRunNotSupported("Selecao de zonas");
}

export async function getZoneStreets(_runId: string, _zoneUid: string): Promise<{ zone_uid: string; streets: string[] }> {
  legacyRunNotSupported("Consulta de ruas da zona");
}

export async function getTransportLayers(viewport: {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
}): Promise<TransportLayersResponse> {
  const bbox = `${viewport.minLon},${viewport.minLat},${viewport.maxLon},${viewport.maxLat}`;
  return (await requestJson(
    `/transport/layers?bbox=${encodeURIComponent(bbox)}`,
    TransportLayersResponseSchema
  )) as TransportLayersResponse;
}

export async function scrapeZoneListings(
  runId: string,
  zoneUid: string,
  streetFilter?: string
): Promise<ListingsScrapeResponse> {
  const payload = {
    search_location_normalized: (streetFilter || "zona").trim().toLowerCase(),
    search_location_label: (streetFilter || "Zona selecionada").trim(),
    search_location_type: "street",
    search_type: "rent"
  };
  const result = await searchZoneListings(runId, zoneUid, payload);
  return {
    zone_uid: zoneUid,
    listings_count: result.total_count
  };
}

export async function finalizeRun(_runId: string): Promise<FinalizeResponse> {
  legacyRunNotSupported("Finalizacao de run");
}

export async function getFinalListings(_runId: string): Promise<ListingsCollection> {
  legacyRunNotSupported("Leitura de listings finalizados");
}

export async function getFinalListingsJson(_runId: string): Promise<FinalListingsJson> {
  legacyRunNotSupported("Leitura de listings finalizados em JSON");
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

export async function getBusStopDetails(stopId: string): Promise<TransportBusDetailResponse> {
  return (await requestJson(
    `/transport/details/bus-stop?stop_id=${encodeURIComponent(stopId)}`,
    TransportBusDetailResponseSchema
  )) as TransportBusDetailResponse;
}

export async function getTransportStopDetails(stopId: string, sourceKind: string): Promise<TransportBusDetailResponse> {
  return (await requestJson(
    `/transport/details/transport-stop?stop_id=${encodeURIComponent(stopId)}&source_kind=${encodeURIComponent(sourceKind)}`,
    TransportBusDetailResponseSchema
  )) as TransportBusDetailResponse;
}

export async function getBusLineDetails(lineId: string): Promise<TransportBusDetailResponse> {
  return (await requestJson(
    `/transport/details/bus-line?line_id=${encodeURIComponent(lineId)}`,
    TransportBusDetailResponseSchema
  )) as TransportBusDetailResponse;
}

export async function updateJourney(
  journeyId: string,
  payload: {
    input_snapshot?: Record<string, unknown>;
    selected_transport_point_id?: string | null;
    selected_zone_id?: string | null;
    selected_property_id?: string | null;
    last_completed_step?: number | null;
    secondary_reference_label?: string | null;
    secondary_reference_point?: { lat: number; lon: number } | null;
  }
): Promise<JourneyRead> {
  return (await requestJson(`/journeys/${journeyId}`, JourneyReadSchema, {
    method: "PATCH",
    body: payload
  })) as JourneyRead;
}

export async function getJourneyZonesList(journeyId: string) {
  return (await requestJson(
    `/journeys/${journeyId}/zones`,
    JourneyZonesListResponseSchema
  )) as z.output<typeof JourneyZonesListResponseSchema>;
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

export async function createZoneEnrichmentJob(journeyId: string): Promise<JobRead> {
  return (await requestJson("/jobs", JobReadSchema, {
    method: "POST",
    body: {
      journey_id: journeyId,
      job_type: "zone_enrichment"
    }
  })) as JobRead;
}

export async function createTransportSearchJob(journeyId: string): Promise<JobRead> {
  return (await requestJson("/jobs", JobReadSchema, {
    method: "POST",
    body: {
      journey_id: journeyId,
      job_type: "transport_search"
    }
  })) as JobRead;
}

export async function getJob(jobId: string): Promise<JobRead> {
  return (await requestJson(`/jobs/${jobId}`, JobReadSchema)) as JobRead;
}

export async function getPriceRollups(
  journeyId: string,
  zoneFingerprint: string,
  searchType: string = "rent",
  days: number = 30
): Promise<PriceRollupRead[]> {
  return (await requestJson(
    `/journeys/${encodeURIComponent(journeyId)}/zones/${encodeURIComponent(zoneFingerprint)}/price-rollups?search_type=${encodeURIComponent(searchType)}&days=${days}`,
    z.array(PriceRollupReadSchema)
  )) as PriceRollupRead[];
}

export async function getZoneListings(
  journeyId: string,
  zoneFingerprint: string,
  searchType: string,
  usageType: string = "residential",
  spatialScope: "inside_zone" | "all" = "inside_zone"
): Promise<ListingsRequestResult> {
  return (await requestJson(
    `/journeys/${encodeURIComponent(journeyId)}/zones/${encodeURIComponent(zoneFingerprint)}/listings?search_type=${encodeURIComponent(searchType)}&usage_type=${encodeURIComponent(usageType)}&spatial_scope=${encodeURIComponent(spatialScope)}`,
    ListingsRequestResultBackendSchema
  )) as ListingsRequestResult;
}

