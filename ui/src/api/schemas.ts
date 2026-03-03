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
  has_transport_data: z.unknown()
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
    lat: number;
    lon: number;
  }>;
  streets_count: number;
  has_street_data: boolean;
  has_poi_data: boolean;
  has_transport_data: boolean;
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

export type FinalListingsJson = Array<Record<string, unknown>>;

export type TransportLayersResponse = {
  routes: GeoJSON.FeatureCollection;
  stops: GeoJSON.FeatureCollection;
};

export type TransportStopsResponse = GeoJSON.FeatureCollection;
