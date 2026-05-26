import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, MapPin } from "lucide-react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { apiActionHint, getZoneFavoriteShare, type FavoriteZoneEntry } from "../../api/client";
import { getPoiCategoryMeta } from "../../domain/poi";
import { formatCurrencyBr, resolvePlatformUrl } from "../../lib/listingFormat";

type SharedZonePageProps = {
  token: string;
};

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_API_KEY || (import.meta.env.MODE === "test" ? "test-maptiler-key" : "");

const mapTilerStyleUrl = (key: string) =>
  `https://api.maptiler.com/maps/bright-v2/style.json?key=${encodeURIComponent(key)}`;

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 text-sm">
      <span className="font-medium text-slate-500">{label}</span>
      <span className="font-semibold text-slate-900">{value}</span>
    </div>
  );
}

function collectGeometryCoordinates(geom: GeoJSON.Geometry | null | undefined): [number, number][] {
  if (!geom) return [];
  const out: [number, number][] = [];
  const visit = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number" && typeof node[1] === "number") {
      out.push([node[0] as number, node[1] as number]);
      return;
    }
    for (const item of node) visit(item);
  };
  if ("coordinates" in geom) {
    visit((geom as { coordinates: unknown }).coordinates);
  }
  return out;
}

const createEmptyStyleImage = (width: number, height: number) => ({
  width,
  height,
  data: new Uint8Array(width * height * 4),
});

const drawPinPath = (context: CanvasRenderingContext2D) => {
  context.beginPath();
  context.moveTo(18, 43);
  context.bezierCurveTo(17.2, 41.9, 6.2, 28.4, 6.2, 16.8);
  context.bezierCurveTo(6.2, 9.2, 11.4, 4.2, 18, 4.2);
  context.bezierCurveTo(24.6, 4.2, 29.8, 9.2, 29.8, 16.8);
  context.bezierCurveTo(29.8, 28.4, 18.8, 41.9, 18, 43);
  context.closePath();
};

const hexToRgb = (hex: string): [number, number, number] => {
  const normalized = hex.replace("#", "");
  const pair = normalized.length === 3 ? normalized.split("").map((c) => `${c}${c}`) : [normalized.slice(0, 2), normalized.slice(2, 4), normalized.slice(4, 6)];
  return [parseInt(pair[0], 16), parseInt(pair[1], 16), parseInt(pair[2], 16)];
};

function createPinIcon(fillHex: string) {
  const width = 36;
  const height = 48;
  if (typeof document === "undefined" || import.meta.env.MODE === "test") {
    return createEmptyStyleImage(width, height);
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return createEmptyStyleImage(width, height);
  context.clearRect(0, 0, width, height);
  context.fillStyle = fillHex;
  context.strokeStyle = "#ffffff";
  context.lineWidth = 2.4;
  context.lineJoin = "round";
  drawPinPath(context);
  context.fill();
  context.stroke();
  context.beginPath();
  context.arc(18, 16.4, 6.3, 0, Math.PI * 2);
  context.fillStyle = "rgba(255,255,255,0.98)";
  context.fill();
  const imageData = context.getImageData(0, 0, width, height);
  return { width, height, data: new Uint8Array(imageData.data) };
}

const createPoiIcon = (fillHex: string, category: string) => {
  const width = 24;
  const height = 24;
  const data = new Uint8Array(width * height * 4);
  const [fr, fg, fb] = hexToRgb(fillHex);

  const setPixel = (x: number, y: number, r: number, g: number, b: number, a: number) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const idx = (y * width + x) * 4;
    data[idx] = r;
    data[idx + 1] = g;
    data[idx + 2] = b;
    data[idx + 3] = a;
  };

  const fillRect = (x0: number, y0: number, w: number, h: number, r: number, g: number, b: number, a: number) => {
    for (let y = y0; y < y0 + h; y += 1) {
      for (let x = x0; x < x0 + w; x += 1) {
        setPixel(x, y, r, g, b, a);
      }
    }
  };

  const fillCircle = (cx: number, cy: number, radius: number, r: number, g: number, b: number, a: number) => {
    const rr = radius * radius;
    for (let y = cy - radius; y <= cy + radius; y += 1) {
      for (let x = cx - radius; x <= cx + radius; x += 1) {
        const dx = x - cx;
        const dy = y - cy;
        if (dx * dx + dy * dy <= rr) {
          setPixel(x, y, r, g, b, a);
        }
      }
    }
  };

  fillCircle(13, 13, 11, fr, fg, fb, 255);

  switch (category) {
    case "school":
      fillRect(8, 9, 10, 7, 255, 255, 255, 240);
      fillRect(10, 7, 6, 2, 255, 255, 255, 240);
      fillRect(9, 16, 2, 3, 255, 255, 255, 240);
      fillRect(15, 16, 2, 3, 255, 255, 255, 240);
      break;
    case "supermarket":
      fillRect(8, 9, 9, 4, 255, 255, 255, 240);
      fillRect(9, 13, 7, 2, 255, 255, 255, 240);
      fillRect(7, 8, 2, 4, 255, 255, 255, 240);
      fillCircle(10, 18, 1, 255, 255, 255, 240);
      fillCircle(15, 18, 1, 255, 255, 255, 240);
      break;
    case "pharmacy":
      fillRect(11, 7, 4, 12, 255, 255, 255, 240);
      fillRect(7, 11, 12, 4, 255, 255, 255, 240);
      break;
    case "park":
      fillCircle(10, 11, 3, 255, 255, 255, 240);
      fillCircle(16, 11, 3, 255, 255, 255, 240);
      fillCircle(13, 8, 4, 255, 255, 255, 240);
      fillRect(12, 13, 2, 5, 255, 255, 255, 240);
      break;
    case "restaurant":
      fillCircle(10, 10, 2, 255, 255, 255, 240);
      fillRect(9, 12, 2, 6, 255, 255, 255, 240);
      fillRect(14, 8, 2, 10, 255, 255, 255, 240);
      fillRect(13, 8, 4, 2, 255, 255, 255, 240);
      break;
    case "gym":
      fillRect(8, 11, 3, 4, 255, 255, 255, 240);
      fillRect(15, 11, 3, 4, 255, 255, 255, 240);
      fillRect(11, 12, 4, 2, 255, 255, 255, 240);
      fillRect(7, 10, 1, 6, 255, 255, 255, 240);
      fillRect(18, 10, 1, 6, 255, 255, 255, 240);
      break;
    default:
      fillCircle(13, 13, 5, 255, 255, 255, 240);
      break;
  }

  return { width, height, data };
};

function addMapImages(map: maplibregl.Map, zone: FavoriteZoneEntry) {
  const zoneColor = zone.color || zone.payload.color || "#0ea5e9";
  if (!map.hasImage("shared-zone-listing-pin")) {
    map.addImage("shared-zone-listing-pin", createPinIcon(zoneColor));
  }
  if (!map.hasImage("shared-zone-transport-pin")) {
    map.addImage("shared-zone-transport-pin", createPinIcon("#7c3aed"));
  }
  for (const category of ["school", "supermarket", "pharmacy", "park", "restaurant", "gym", "default"] as const) {
    const meta = getPoiCategoryMeta(category === "default" ? undefined : category);
    if (!map.hasImage(meta.iconId)) {
      map.addImage(meta.iconId, createPoiIcon(meta.color, category));
    }
  }
}

function buildMapData(zone: FavoriteZoneEntry) {
  const zoneColor = zone.color || zone.payload.color || "#0ea5e9";
  const zoneFeatures: GeoJSON.Feature<GeoJSON.Geometry>[] = zone.payload.isochrone_geom
    ? [{
        type: "Feature",
        geometry: zone.payload.isochrone_geom as GeoJSON.Geometry,
        properties: { color: zoneColor },
      }]
    : [];
  const poiFeatures: GeoJSON.Feature<GeoJSON.Point>[] = (zone.payload.poi_points || []).map((poi, index) => {
    const meta = getPoiCategoryMeta(poi.category);
    return {
      type: "Feature",
      geometry: { type: "Point", coordinates: [poi.lon, poi.lat] },
      properties: {
        id: poi.id || `poi:${index}`,
        name: poi.name || "Ponto de interesse sem nome",
        icon_id: meta.iconId,
      },
    };
  });
  const listingFeatures: GeoJSON.Feature<GeoJSON.Point>[] = (zone.payload.listings || [])
    .filter((listing) => typeof listing.lat === "number" && typeof listing.lon === "number")
    .map((listing, index) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [listing.lon as number, listing.lat as number] },
      properties: {
        id: listing.property_id || listing.platform_listing_id || `listing:${index}`,
        icon_id: "shared-zone-listing-pin",
      },
    }));
  const tp = zone.payload.transport_point;
  const transportFeatures: GeoJSON.Feature<GeoJSON.Point>[] = tp?.lat != null && tp?.lon != null
    ? [{
        type: "Feature",
        geometry: { type: "Point", coordinates: [tp.lon, tp.lat] },
        properties: { icon_id: "shared-zone-transport-pin" },
      }]
    : [];
  return { zoneFeatures, poiFeatures, listingFeatures, transportFeatures };
}

function SharedZoneMap({ zone }: { zone: FavoriteZoneEntry }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (!MAPTILER_KEY) {
      setMapError("Configure VITE_MAPTILER_API_KEY para exibir o mapa da zona compartilhada.");
      return;
    }

    const data = buildMapData(zone);
    const coords = collectGeometryCoordinates(zone.payload.isochrone_geom as GeoJSON.Geometry | null);
    const center = coords[0] || [-46.63331, -23.55052];
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapTilerStyleUrl(MAPTILER_KEY),
      center,
      zoom: 12,
      attributionControl: { compact: true },
      pitchWithRotate: false,
      dragRotate: false,
    });
    mapRef.current = map;

    map.on("load", () => {
      addMapImages(map, zone);
      map.addSource("shared-zone-source", { type: "geojson", data: { type: "FeatureCollection", features: data.zoneFeatures } });
      map.addSource("shared-zone-pois-source", { type: "geojson", data: { type: "FeatureCollection", features: data.poiFeatures } });
      map.addSource("shared-zone-listings-source", { type: "geojson", data: { type: "FeatureCollection", features: data.listingFeatures } });
      map.addSource("shared-zone-transport-source", { type: "geojson", data: { type: "FeatureCollection", features: data.transportFeatures } });
      map.addLayer({
        id: "shared-zone-fill-layer",
        type: "fill",
        source: "shared-zone-source",
        paint: { "fill-color": ["get", "color"], "fill-opacity": 0.16 },
      });
      map.addLayer({
        id: "shared-zone-outline-layer",
        type: "line",
        source: "shared-zone-source",
        paint: { "line-color": ["get", "color"], "line-width": 2.4, "line-opacity": 0.95 },
      });
      map.addLayer({
        id: "shared-zone-pois-layer",
        type: "symbol",
        source: "shared-zone-pois-source",
        layout: { "icon-image": ["get", "icon_id"], "icon-size": 0.54, "icon-allow-overlap": true },
      });
      map.addLayer({
        id: "shared-zone-transport-layer",
        type: "symbol",
        source: "shared-zone-transport-source",
        layout: { "icon-image": ["get", "icon_id"], "icon-size": 0.54, "icon-anchor": "bottom", "icon-allow-overlap": true },
      });
      map.addLayer({
        id: "shared-zone-listings-layer",
        type: "symbol",
        source: "shared-zone-listings-source",
        layout: { "icon-image": ["get", "icon_id"], "icon-size": 0.58, "icon-anchor": "bottom", "icon-allow-overlap": true },
      });
      if (coords.length > 0) {
        const bounds = coords.reduce(
          (box, coord) => box.extend(coord),
          new maplibregl.LngLatBounds(coords[0], coords[0]),
        );
        map.fitBounds(bounds, { padding: 48, duration: 0, maxZoom: 15 });
      }
    });

    map.on("error", () => {
      setMapError("Não foi possível carregar o mapa da zona compartilhada.");
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [zone]);

  return (
    <div className="relative h-[55vh] min-h-[24rem] overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 shadow-sm lg:h-[calc(100vh-4rem)]">
      <div ref={containerRef} className="h-full w-full" aria-label="Mapa da zona compartilhada" />
      {mapError ? (
        <div className="absolute inset-0 flex items-center justify-center bg-white/92 px-6 text-center text-sm font-medium text-rose-700">
          {mapError}
        </div>
      ) : null}
    </div>
  );
}

export function SharedZonePage({ token }: SharedZonePageProps) {
  const query = useQuery({
    queryKey: ["shared-zone", token],
    queryFn: async () => getZoneFavoriteShare(token),
    retry: false,
  });

  const zone = query.data;
  const metrics = zone?.payload.metrics || {};
  const transport = zone?.payload.transport_summary;
  const propertyTypes = useMemo(
    () => Object.entries(zone?.payload.property_type_counts || {}).filter(([, count]) => Number(count) > 0),
    [zone?.payload.property_type_counts],
  );

  if (query.isLoading) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">Carregando zona compartilhada...</main>;
  }

  if (query.error || !zone) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="max-w-md rounded-2xl border border-rose-200 bg-white p-6 text-sm text-rose-700 shadow-sm">
          {apiActionHint(query.error || new Error("Compartilhamento não encontrado."))}
        </div>
      </main>
    );
  }

  const zoneName = zone.payload.neighborhood_name
    ? `${zone.payload.neighborhood_name}${zone.payload.city_name ? ` · ${zone.payload.city_name}` : ""}`
    : `Zona ${zone.zoneFingerprint.slice(0, 8)}`;
  const zoneColor = zone.color || zone.payload.color || "#0ea5e9";

  return (
    <main className="min-h-screen bg-slate-50 p-4 text-slate-900 lg:p-8">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(22rem,0.8fr)]">
        <SharedZoneMap zone={zone} />
        <div className="space-y-5">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Zona compartilhada</p>
                <h1 className="mt-2 text-2xl font-bold tracking-tight">{zoneName}</h1>
                <p className="mt-1 text-sm text-slate-500">Visualização somente leitura.</p>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700">
                <span className="h-4 w-4 rounded-full" style={{ backgroundColor: zoneColor }} />
                {zoneColor}
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900">Métricas</h2>
            <div className="mt-4 grid gap-2">
              <MetricRow label="Tempo" value={metrics.travel_time_minutes != null ? `${metrics.travel_time_minutes} min` : "--"} />
              <MetricRow label="Área" value={metrics.zone_area_m2 != null ? `${(metrics.zone_area_m2 / 1_000_000).toFixed(2)} km²` : "--"} />
              <MetricRow label="Verde" value={metrics.green_percentage != null ? `${metrics.green_percentage.toFixed(1)}%` : "--"} />
              <MetricRow label="Alagamento" value={metrics.flood_percentage != null ? `${metrics.flood_percentage.toFixed(1)}%` : "--"} />
              <MetricRow label="Preço médio" value={metrics.zone_average_price != null ? formatCurrencyBr(metrics.zone_average_price) : "--"} />
              <MetricRow label="Preço m²" value={metrics.zone_average_unit_price != null ? `${formatCurrencyBr(metrics.zone_average_unit_price)}/m²` : "--"} />
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900">Transporte e imóveis</h2>
            <div className="mt-4 grid gap-2">
              <MetricRow label="Pontos de ônibus" value={String(transport?.bus_stop_count ?? 0)} />
              <MetricRow label="Linhas nos pontos" value={String(transport?.bus_stop_line_count ?? transport?.bus_line_count ?? 0)} />
              <MetricRow label="Terminais" value={String(transport?.bus_terminal_count ?? 0)} />
              <MetricRow label="Estações trem/metrô" value={String(transport?.train_metro_station_count ?? transport?.train_metro_platform_count ?? 0)} />
              <MetricRow label="Linhas trem/metrô" value={String(transport?.train_metro_line_count ?? 0)} />
              {propertyTypes.map(([type, count]) => (
                <MetricRow key={type} label={type === "residential" ? "Residenciais" : type === "commercial" ? "Comerciais" : type} value={String(count)} />
              ))}
            </div>
            <details className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600">
              <summary className="cursor-pointer font-semibold text-slate-800">Ver nomes de linhas</summary>
              <div className="mt-3 max-h-44 overflow-y-auto space-y-3">
                <div>
                  <p className="mb-1 font-bold uppercase tracking-[0.12em] text-slate-500">Ônibus</p>
                  <p>{(transport?.bus_line_names || []).join(", ") || "Nomes indisponíveis."}</p>
                </div>
                <div>
                  <p className="mb-1 font-bold uppercase tracking-[0.12em] text-slate-500">Trem e metrô</p>
                  <p>{(transport?.train_metro_line_names || []).join(", ") || "Nomes indisponíveis."}</p>
                </div>
              </div>
            </details>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900">Pontos de interesse</h2>
            <div className="mt-4 grid gap-2">
              {(zone.payload.poi_points || []).length === 0 ? <p className="text-sm text-slate-500">Nenhum ponto de interesse salvo no snapshot.</p> : null}
              {(zone.payload.poi_points || []).map((poi, index) => {
                const meta = getPoiCategoryMeta(poi.category);
                return (
                  <div key={`${poi.id || index}`} className="flex items-start gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                    <MapPin className="mt-0.5 h-4 w-4" style={{ color: meta.color }} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{poi.name || "Ponto de interesse sem nome"}</p>
                      <p className="text-xs text-slate-500">{meta.label}{poi.address ? ` · ${poi.address}` : ""}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900">Imóveis salvos no snapshot</h2>
            <div className="mt-4 grid gap-3">
              {(zone.payload.listings || []).length === 0 ? <p className="text-sm text-slate-500">Nenhum imóvel salvo no snapshot.</p> : null}
              {(zone.payload.listings || []).map((listing, index) => {
                const href = resolvePlatformUrl(listing.url, listing.platform);
                return (
                  <article key={`${listing.property_id || listing.platform_listing_id || index}`} className="rounded-xl border border-slate-200 p-3">
                    <p className="text-sm font-semibold">{listing.address_normalized || "Endereço não informado"}</p>
                    <p className="mt-1 text-xs text-slate-500">{listing.neighborhood_name || "Bairro não informado"}</p>
                    {href ? (
                      <a href={href} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-pastel-violet-700 hover:text-pastel-violet-900">
                        Abrir anúncio
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
