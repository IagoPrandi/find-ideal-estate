import { z } from "zod";

export const RunStatusSchema = z.object({
  state: z.string(),
  stage: z.string(),
  updated_at: z.string().optional(),
  created_at: z.string().optional()
});

export const RunCreateResponseSchema = z.object({
  run_id: z.string(),
  status: RunStatusSchema
});

export const RunStatusResponseSchema = z.object({
  run_id: z.string(),
  status: RunStatusSchema
});

export const ZoneFeatureSchema = z.object({
  type: z.literal("Feature"),
  geometry: z
    .object({
      type: z.string(),
      coordinates: z.unknown()
    })
    .passthrough(),
  properties: z
    .object({
      zone_uid: z.string(),
      centroid_lat: z.number().optional(),
      centroid_lon: z.number().optional(),
      time_agg: z.number().optional(),
      score: z.number().optional()
    })
    .passthrough()
});

export const ZonesCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(ZoneFeatureSchema)
});

// Backend: GET /journeys/{journey_id}/zones
export const JourneyZoneReadSchema = z.object({
  id: z.string(),
  journey_id: z.string(),
  transport_point_id: z.string().nullable().optional(),
  fingerprint: z.string(),
  state: z.string(),
  is_circle_fallback: z.boolean().optional().default(false),
  travel_time_minutes: z.number().nullable().optional(),
  walk_distance_meters: z.number().nullable().optional(),
  isochrone_geom: z.any(),
  green_area_m2: z.number().nullable().optional(),
  green_vegetation_level: z.string().nullable().optional(),
  green_vegetation_label: z.string().nullable().optional(),
  flood_area_m2: z.number().nullable().optional(),
  safety_incidents_count: z.number().nullable().optional(),
  poi_counts: z.record(z.number()).nullable().optional(),
  poi_points: z.array(
    z.object({
      kind: z.string().optional().default("poi"),
      id: z.string().nullable().optional(),
      name: z.string().nullable().optional(),
      category: z.string().nullable().optional(),
      address: z.string().nullable().optional(),
      lat: z.number(),
      lon: z.number()
    })
  ).nullable().optional(),
  badges: z.any().nullable().optional(),
  badges_provisional: z.any().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional()
});

export const JourneyZonesListResponseSchema = z.object({
  zones: z.array(JourneyZoneReadSchema),
  total_count: z.number().optional(),
  completed_count: z.number().optional()
});

// Backend: GET /journeys/{journey_id}/listings/address-suggest?zone_fingerprint=...&q=...
export const SearchAddressSuggestionBackendSchema = z.object({
  label: z.string(),
  normalized: z.string(),
  location_type: z.string(),
  lat: z.number(),
  lon: z.number()
});

// Backend: POST /journeys/{journey_id}/listings/search
export const ListingCardReadBackendSchema = z.object({
  // Campos principais retornados pelo listing scraper
  property_id: z.string().nullable().optional(),
  address_normalized: z.string().nullable().optional(),
  area_m2: z.number().nullable().optional(),
  bedrooms: z.number().nullable().optional(),
  bathrooms: z.number().nullable().optional(),
  parking: z.number().nullable().optional(),
  usage_type: z.string().nullable().optional(),
  platform: z.string().nullable().optional(),
  platform_listing_id: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  image_url: z.string().nullable().optional(),
  lat: z.number().nullable().optional(),
  lon: z.number().nullable().optional(),
  has_coordinates: z.boolean().optional().default(false),
  inside_zone: z.boolean().optional().default(false),
  platforms_available: z.array(z.string()).optional().default([]),

  // Preços atuais (o scraper pode retornar strings, ex: Decimal -> str)
  current_best_price: z.string().nullable().optional(),
  condo_fee: z.string().nullable().optional(),
  iptu: z.string().nullable().optional(),
  second_best_price: z.string().nullable().optional(),
  duplication_badge: z.string().nullable().optional(),
  observed_at: z.string().nullable().optional(),

  // Mantém flexibilidade caso a API adicione campos no futuro
  price: z.any().optional()
}).passthrough();

export const ListingsRequestResultBackendSchema = z.object({
  source: z.string(),
  job_id: z.string().nullable().optional(),
  freshness_status: z.string().nullable().optional(),
  upgrade_reason: z.string().nullable().optional(),
  next_refresh_window: z.string().nullable().optional(),
  listings: z.array(ListingCardReadBackendSchema).default([]),
  total_count: z.number(),
  cache_age_hours: z.number().nullable().optional()
});

export const ListingsScrapePlatformDiagnosticsSchema = z.object({
  status: z.string().optional(),
  sequence: z.number().nullable().optional(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  scrape_started_at: z.string().nullable().optional(),
  scrape_finished_at: z.string().nullable().optional(),
  persist_started_at: z.string().nullable().optional(),
  persist_finished_at: z.string().nullable().optional(),
  scrape_duration_ms: z.number().nullable().optional(),
  persist_duration_ms: z.number().nullable().optional(),
  total_duration_ms: z.number().nullable().optional(),
  scraped_count: z.number().nullable().optional(),
  persisted_count: z.number().nullable().optional(),
  error_phase: z.string().nullable().optional(),
  error_type: z.string().nullable().optional(),
  error_message: z.string().nullable().optional()
});

export const ListingsScrapeDiagnosticsSchema = z.object({
  status: z.string().optional(),
  started_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  total_duration_ms: z.number().nullable().optional(),
  active_platform: z.string().nullable().optional(),
  search_address: z.string().nullable().optional(),
  cache_status: z.string().nullable().optional(),
  cache_status_before: z.string().nullable().optional(),
  platform_order: z.array(z.string()).optional().default([]),
  summary: z.object({
    total_scraped: z.number().nullable().optional(),
    platforms_completed: z.array(z.string()).optional().default([]),
    platforms_failed: z.array(z.string()).optional().default([])
  }).optional(),
  platforms: z.record(ListingsScrapePlatformDiagnosticsSchema).optional().default({})
});

export type ListingsScrapePlatformDiagnostics = z.output<typeof ListingsScrapePlatformDiagnosticsSchema>;
export type ListingsScrapeDiagnostics = z.output<typeof ListingsScrapeDiagnosticsSchema>;

export const ListingsScrapePlanPlatformSchema = z.object({
  platform: z.string(),
  max_pages: z.number()
});

export const ListingsScrapePlanResponseSchema = z.object({
  search_type: z.string(),
  usage_type: z.string(),
  total_pages: z.number(),
  platforms: z.array(ListingsScrapePlanPlatformSchema)
});

export const ZoneDetailResponseSchema = z.object({
  zone_uid: z.string(),
  zone_name: z.string(),
  green_area_ratio: z.number(),
  flood_area_ratio: z.number(),
  poi_count_by_category: z.record(z.number()),
  bus_lines_count: z.number(),
  train_lines_count: z.number(),
  bus_stop_count: z.number(),
  train_station_count: z.number(),
  lines_used_for_generation: z.array(
    z.object({
      mode: z.string(),
      route_id: z.string(),
      line_name: z.string()
    })
  ),
  reference_transport_point: z.unknown().optional(),
  seed_transport_point: z.unknown().optional(),
  downstream_transport_point: z.unknown().optional(),
  transport_points: z.array(z.unknown()),
  poi_points: z.array(z.unknown()),
  streets_count: z.number(),
  has_street_data: z.unknown(),
  has_poi_data: z.unknown(),
  has_transport_data: z.unknown(),
  public_safety: z.unknown().optional()
});

export const SimpleMessageResponseSchema = z.object({
  message: z.string()
});

export const ListingsScrapeResponseSchema = z.object({
  zone_uid: z.string(),
  listings_count: z.number()
});

export const FinalizeResponseSchema = z.object({
  listings_final_json: z.string(),
  listings_final_csv: z.string(),
  listings_final_geojson: z.string(),
  zones_final_geojson: z.string()
});

export const ListingFeatureSchema = z.object({
  type: z.literal("Feature"),
  geometry: z.object({
    type: z.literal("Point"),
    coordinates: z.tuple([z.number(), z.number()])
  }),
  properties: z.record(z.unknown())
});

export const ListingsCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(ListingFeatureSchema)
});

export const FinalListingsJsonSchema = z.array(z.record(z.unknown()));

export const PriceRollupReadSchema = z.object({
  id: z.string(),
  date: z.string(),
  zone_fingerprint: z.string(),
  search_type: z.string(),
  median_price: z.string().optional(),
  p25_price: z.string().optional(),
  p75_price: z.string().optional(),
  sample_count: z.number(),
  computed_at: z.string()
});

export type PriceRollupRead = {
  id: string;
  date: string;
  zone_fingerprint: string;
  search_type: string;
  median_price?: string;
  p25_price?: string;
  p75_price?: string;
  sample_count: number;
  computed_at: string;
};

export const TransportFeatureSchema = z.object({
  type: z.literal("Feature"),
  geometry: z
    .object({
      type: z.string(),
      coordinates: z.unknown()
    })
    .passthrough(),
  properties: z.record(z.unknown())
});

export const TransportLayersResponseSchema = z.object({
  routes: z.object({
    type: z.literal("FeatureCollection"),
    features: z.array(TransportFeatureSchema)
  }),
  stops: z.object({
    type: z.literal("FeatureCollection"),
    features: z.array(TransportFeatureSchema)
  })
});

export const TransportStopsResponseSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(TransportFeatureSchema)
});

export const TransportPointReadSchema = z.object({
  id: z.string(),
  journey_id: z.string(),
  source: z.string(),
  external_id: z.string().nullish(),
  name: z.string().nullish(),
  lat: z.number(),
  lon: z.number(),
  walk_time_sec: z.number(),
  walk_distance_m: z.number(),
  route_ids: z.array(z.string()),
  modal_types: z.array(z.string()),
  route_count: z.number(),
  created_at: z.string()
});

export const TransportBusDetailResponseSchema = z.object({
  count: z.number(),
  buses: z.array(z.string()).default([]),
  source: z.string()
});

export const JourneyReadSchema = z.object({
  id: z.string(),
  user_id: z.string().nullish(),
  anonymous_session_id: z.string().nullish(),
  state: z.string(),
  input_snapshot: z.record(z.unknown()).nullish(),
  selected_transport_point_id: z.string().nullish(),
  selected_zone_id: z.string().nullish(),
  selected_property_id: z.string().nullish(),
  last_completed_step: z.number().nullish(),
  secondary_reference_label: z.string().nullish(),
  secondary_reference_point: z.object({ lat: z.number(), lon: z.number() }).nullish(),
  created_at: z.string(),
  updated_at: z.string(),
  expires_at: z.string().nullish()
});

export const JobReadSchema = z.object({
  id: z.string(),
  journey_id: z.string().nullish(),
  job_type: z.string(),
  state: z.string(),
  progress_percent: z.number().nullish().transform((v) => v ?? 0),
  current_stage: z.string().nullish(),
  cancel_requested_at: z.string().nullish(),
  started_at: z.string().nullish(),
  finished_at: z.string().nullish(),
  worker_id: z.string().nullish(),
  result_ref: z.record(z.unknown()).nullish(),
  error_code: z.string().nullish(),
  error_message: z.string().nullish(),
  created_at: z.string()
});

export type RunCreateResponse = {
  run_id: string;
  status: {
    state: string;
    stage: string;
    updated_at?: string;
    created_at?: string;
  };
};

export type RunStatusResponse = {
  run_id: string;
  status: {
    state: string;
    stage: string;
    updated_at?: string;
    created_at?: string;
  };
};

export type ZonesCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: {
      type: string;
      coordinates: unknown;
    };
    properties: {
      zone_uid: string;
      centroid_lat?: number;
      centroid_lon?: number;
      time_agg?: number;
      score?: number;
      [key: string]: unknown;
    };
  }>;
};

export type ZoneDetailResponse = {
  zone_uid: string;
  zone_name: string;
  green_area_ratio: number;
  flood_area_ratio: number;
  poi_count_by_category: Record<string, number>;
  bus_lines_count: number;
  train_lines_count: number;
  bus_stop_count: number;
  train_station_count: number;
  lines_used_for_generation: Array<{
    mode: string;
    route_id: string;
    line_name: string;
  }>;
  reference_transport_point?: {
    kind: string;
    id?: unknown;
    name?: string;
    lat?: number;
    lon?: number;
  } | null;
  seed_transport_point?: {
    kind: string;
    id?: string | null;
    name?: string | null;
    category?: string | null;
    lat: number;
    lon: number;
  } | null;
  downstream_transport_point?: {
    kind: string;
    id?: string | null;
    name?: string | null;
    category?: string | null;
    lat: number;
    lon: number;
  } | null;
  transport_points: Array<{
    kind: string;
    id?: string | null;
    name?: string | null;
    category?: string | null;
    lat: number;
    lon: number;
  }>;
  poi_points: Array<{
    kind: string;
    id?: string | null;
    name?: string | null;
    category?: string | null;
    address?: string | null;
    lat: number;
    lon: number;
  }>;
  streets_count: number;
  has_street_data: boolean;
  has_poi_data: boolean;
  has_transport_data: boolean;
  public_safety?: {
    enabled?: boolean;
    year?: number;
    radius_km?: number;
    summary?: {
      ocorrencias_no_raio_total?: number;
      delta_pct_vs_cidade?: number | null;
      top_delitos_no_raio?: Array<{
        tipo_delito: string;
        qtd: number;
      }>;
      delegacias_mais_proximas?: Array<{
        nome: string;
        dist_km?: number;
        total_ocorrencias?: number;
      }>;
    };
    result?: Record<string, unknown>;
    error?: string;
  } | null;
};

export type SimpleMessageResponse = {
  message: string;
};

export type ListingsScrapeResponse = {
  zone_uid: string;
  listings_count: number;
};

export type FinalizeResponse = {
  listings_final_json: string;
  listings_final_csv: string;
  listings_final_geojson: string;
  zones_final_geojson: string;
};

export type ListingsCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: {
      type: "Point";
      coordinates: [number, number];
    };
    properties: Record<string, unknown>;
  }>;
};

export type ListingsScrapePlanPlatform = z.output<typeof ListingsScrapePlanPlatformSchema>;
export type ListingsScrapePlanResponse = z.output<typeof ListingsScrapePlanResponseSchema>;

export type FinalListingsJson = Array<Record<string, unknown>>;

export type TransportLayersResponse = {
  routes: GeoJSON.FeatureCollection;
  stops: GeoJSON.FeatureCollection;
};

export type TransportStopsResponse = GeoJSON.FeatureCollection;

export type TransportBusDetailResponse = {
  count: number;
  buses: string[];
  source: string;
};

export type TransportPointRead = {
  id: string;
  journey_id: string;
  source: string;
  external_id?: string | null;
  name?: string | null;
  lat: number;
  lon: number;
  walk_time_sec: number;
  walk_distance_m: number;
  route_ids: string[];
  modal_types: string[];
  route_count: number;
  created_at: string;
};

export type JourneyRead = {
  id: string;
  user_id?: string | null;
  anonymous_session_id?: string | null;
  state: string;
  input_snapshot?: Record<string, unknown> | null;
  selected_transport_point_id?: string | null;
  selected_zone_id?: string | null;
  selected_property_id?: string | null;
  last_completed_step?: number | null;
  secondary_reference_label?: string | null;
  secondary_reference_point?: { lat: number; lon: number } | null;
  created_at: string;
  updated_at: string;
  expires_at?: string | null;
};

export type JobRead = {
  id: string;
  journey_id?: string | null;
  job_type: string;
  state: string;
  progress_percent: number;
  current_stage?: string | null;
  cancel_requested_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  worker_id?: string | null;
  result_ref?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
};
