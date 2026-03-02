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
  streets_path: z.string(),
  pois_path: z.string(),
  transport_path: z.string()
});

export const SimpleMessageResponseSchema = z.object({
  message: z.string()
});

export const ListingsScrapeResponseSchema = z.object({
  zone_uid: z.string(),
  listing_files: z.array(z.string())
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
  streets_path: string;
  pois_path: string;
  transport_path: string;
};

export type SimpleMessageResponse = {
  message: string;
};

export type ListingsScrapeResponse = {
  zone_uid: string;
  listing_files: string[];
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

export type TransportLayersResponse = {
  routes: GeoJSON.FeatureCollection;
  stops: GeoJSON.FeatureCollection;
};

export type TransportStopsResponse = GeoJSON.FeatureCollection;
