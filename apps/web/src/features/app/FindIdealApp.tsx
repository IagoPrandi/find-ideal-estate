import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { API_BASE, getJourneyTransportPoints, getJourneyZonesList, getZoneListings } from "../../api/client";
import { WizardPanel } from "../../components/panels";
import { applyListingsPanelFilters, getListingDisplayPrice, getListingSelectionKey } from "../../lib/listingFormat";
import { useJourneyStore, useUIStore } from "../../state";

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_API_KEY || (import.meta.env.MODE === "test" ? "test-maptiler-key" : "");

const mapTilerStyleUrl = (key: string) =>
  `https://api.maptiler.com/maps/bright-v2/style.json?key=${encodeURIComponent(key)}`;

const apiTileUrl = (path: string) => `${API_BASE}${path}`;

const BUS_LAYER_LIST = ["bus-line-layer", "bus-stop-layer", "bus-terminal-layer"] as const;
const TRANSPORT_CANDIDATES_SOURCE_ID = "transport-candidates-source-runtime";
const ZONES_SOURCE_ID = "journey-zones-source-runtime";
const LISTINGS_SOURCE_ID = "journey-listings-source-runtime";

const EMPTY_FEATURE_COLLECTION: GeoJSON.FeatureCollection<GeoJSON.Geometry> = {
  type: "FeatureCollection",
  features: []
};

const setGeoJsonSourceData = (map: maplibregl.Map, sourceId: string, data: GeoJSON.FeatureCollection<GeoJSON.Geometry>) => {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  }
};

const toTransportCandidatesFeatureCollection = (points: Array<{ id: string; lon: number; lat: number; name?: string | null; route_count: number }>, selectedTransportId: string | null): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: points.map((point) => ({
    type: "Feature",
    geometry: {
      type: "Point",
      coordinates: [point.lon, point.lat]
    },
    properties: {
      id: point.id,
      name: point.name || "Ponto de transporte",
      route_count: point.route_count,
      selected: point.id === selectedTransportId
    }
  }))
});

const toZonesFeatureCollection = (
  zones: Array<{ id: string; fingerprint: string; travel_time_minutes?: number | null; isochrone_geom?: unknown }>,
  selectedZoneFingerprint: string | null
): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: zones
    .filter((zone) => Boolean(zone.isochrone_geom && typeof zone.isochrone_geom === "object"))
    .map((zone, index) => ({
      type: "Feature",
      geometry: zone.isochrone_geom as GeoJSON.Geometry,
      properties: {
        id: zone.id,
        fingerprint: zone.fingerprint,
        label: zone.travel_time_minutes ? `${index + 1} · ${zone.travel_time_minutes}m` : String(index + 1),
        selected: zone.fingerprint === selectedZoneFingerprint
      }
    }))
});

const toListingsFeatureCollection = (
  listings: Array<Record<string, unknown>>,
  selectedListingKey: string | null
): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: listings
    .filter((listing) => typeof listing.lon === "number" && typeof listing.lat === "number")
    .map((listing) => {
      const listingKey = getListingSelectionKey(listing as never);
      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [listing.lon as number, listing.lat as number]
        },
        properties: {
          listing_key: listingKey,
          platform: String(listing.platform || "Plataforma"),
          price: getListingDisplayPrice(listing as never) || 0,
          selected: listingKey !== "" && listingKey === selectedListingKey
        }
      };
    })
});

const hexToRgb = (hex: string): [number, number, number] => {
  const normalized = hex.replace("#", "");
  const pair = normalized.length === 3 ? normalized.split("").map((c) => `${c}${c}`) : [normalized.slice(0, 2), normalized.slice(2, 4), normalized.slice(4, 6)];
  return [parseInt(pair[0], 16), parseInt(pair[1], 16), parseInt(pair[2], 16)];
};

const createBusIcon = (fillHex: string) => {
  const width = 28;
  const height = 28;
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

  fillRect(4, 6, 20, 14, fr, fg, fb, 255);
  fillRect(7, 9, 14, 5, 255, 255, 255, 230);
  fillRect(6, 18, 16, 2, 255, 255, 255, 224);
  fillCircle(9, 22, 2, fr, fg, fb, 255);
  fillCircle(19, 22, 2, fr, fg, fb, 255);

  return { width, height, data };
};

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

const parseBusList = (rawValue: unknown) => {
  if (typeof rawValue !== "string" || !rawValue.trim()) {
    return [];
  }
  const items = rawValue
    .split("||")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return items;
};

const popupContent = (title: string, name: string, busCountLabel: string, buses: string[]) => {
  const listItems = buses.map((bus) => `<li style="margin-bottom:4px;">${escapeHtml(bus)}</li>`).join("");
  const listSection =
    buses.length > 0
      ? `<ul style="margin:0; padding-left:16px; max-height:140px; overflow:auto; font-size:12px; color:#334155;">${listItems}</ul>`
      : '<p style="margin:0; font-size:12px; color:#64748b;">Dados de linhas e sentido indisponíveis para esta feição.</p>';
  return `
    <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
      <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">${escapeHtml(title)}</p>
      <p style="margin:0 0 10px; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(name)}</p>
      <p style="margin:0 0 8px; font-size:12px; color:#0f172a;">
        Ônibus identificados: <strong>${busCountLabel}</strong>
      </p>
      ${listSection}
    </div>
  `;
};

export function FindIdealApp() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const busPopupRef = useRef<maplibregl.Popup | null>(null);
  const pickedMarkerRef = useRef<maplibregl.Marker | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const step = useUIStore((state) => state.step);
  const pickedCoord = useJourneyStore((state) => state.pickedCoord);
  const setPickedCoord = useJourneyStore((state) => state.setPickedCoord);
  const journeyId = useJourneyStore((state) => state.journeyId);
  const selectedTransportId = useJourneyStore((state) => state.selectedTransportId);
  const selectedZoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const selectedListingKey = useJourneyStore((state) => state.selectedListingKey);
  const listingsJobId = useJourneyStore((state) => state.listingsJobId);
  const listingsFilters = useJourneyStore((state) => state.listingsFilters);
  const config = useJourneyStore((state) => state.config);
  const setSelectedTransportId = useJourneyStore((state) => state.setSelectedTransportId);
  const setSelectedListingKey = useJourneyStore((state) => state.setSelectedListingKey);
  const setSelectedZone = useJourneyStore((state) => state.setSelectedZone);
  const stepRef = useRef(step);
  const layerVisibility = {
    routes: true,
    metro: true,
    train: true,
    busStops: true,
    flood: true,
    green: true,
  };

  useEffect(() => {
    stepRef.current = step;
  }, [step]);

  const listingsQuery = useQuery({
    queryKey: ["zone-listings", journeyId, selectedZoneFingerprint, config.type, "all"],
    queryFn: async () => getZoneListings(journeyId as string, selectedZoneFingerprint as string, config.type, "residential", "all"),
    enabled: Boolean(journeyId && selectedZoneFingerprint && step >= 6),
    refetchInterval: (query) => {
      if (step < 6) {
        return false;
      }
      const data = query.state.data;
      if (!data) {
        return 5000;
      }
      const emptyResults = (data.total_count || 0) === 0;
      return data.source === "none" || data.freshness_status === "no_cache" || emptyResults || Boolean(listingsJobId) ? 5000 : false;
    }
  });

  const filteredMapListings = useMemo(
    () => applyListingsPanelFilters(listingsQuery.data?.listings || [], listingsFilters),
    [listingsFilters, listingsQuery.data?.listings]
  );

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!MAPTILER_KEY) {
      setMapError("Defina VITE_MAPTILER_API_KEY no .env do frontend para renderizar o mapa.");
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapTilerStyleUrl(MAPTILER_KEY),
      center: [-46.633308, -23.55052],
      zoom: 10.7,
      pitchWithRotate: false,
      dragRotate: false,
    });

    mapRef.current = map;

    map.on("load", () => {
      if (!map.hasImage("bus-stop-icon")) {
        map.addImage("bus-stop-icon", createBusIcon("#845ef7"));
      }
      if (!map.hasImage("bus-terminal-icon")) {
        map.addImage("bus-terminal-icon", createBusIcon("#f97316"));
      }

      map.addSource("transport-lines-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/lines/{z}/{x}/{y}.pbf")],
        minzoom: 8,
        maxzoom: 16,
        attribution: "Dados GTFS + GeoSampa",
      });

      map.addSource("transport-stops-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/stops/{z}/{x}/{y}.pbf")],
        minzoom: 9,
        maxzoom: 17,
        attribution: "Dados GTFS + GeoSampa",
      });

      map.addSource("green-areas-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/environment/green/{z}/{x}/{y}.pbf")],
        minzoom: 9,
        maxzoom: 17,
        attribution: "GeoSampa",
      });

      map.addSource("flood-areas-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/environment/flood/{z}/{x}/{y}.pbf")],
        minzoom: 9,
        maxzoom: 17,
        attribution: "GeoSampa",
      });

      map.addSource(TRANSPORT_CANDIDATES_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(ZONES_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(LISTINGS_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addLayer({
        id: "bus-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "bus"],
        paint: {
          "line-color": "#845ef7",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 12, 2.2, 15, 3.5],
          "line-opacity": 0.72,
          "line-dasharray": [1.4, 1.1],
        },
      });

      map.addLayer({
        id: "bus-line-direction-layer",
        type: "symbol",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "bus"],
        layout: {
          "symbol-placement": "line",
          "symbol-spacing": 170,
          "text-field": "▶",
          "text-size": 11,
          "text-keep-upright": false,
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#5b3fd6",
          "text-opacity": 0.76,
        },
      });

      map.addLayer({
        id: "metro-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "metro"],
        paint: {
          "line-color": "#e11d48",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.8, 12, 3.2, 15, 4.8],
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "train-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "train"],
        paint: {
          "line-color": "#0f766e",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.5, 12, 2.8, 15, 4.2],
          "line-opacity": 0.88,
        },
      });

      map.addLayer({
        id: "flood-layer",
        type: "fill",
        source: "flood-areas-source",
        "source-layer": "flood_areas",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#378add",
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.12, 13, 0.2, 16, 0.3],
        },
      });

      map.addLayer({
        id: "green-layer",
        type: "fill",
        source: "green-areas-source",
        "source-layer": "green_areas",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#6a9f2b",
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.1, 13, 0.18, 16, 0.28],
        },
      });

      map.addLayer({
        id: "bus-stop-layer",
        type: "symbol",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "bus_stop"],
        layout: {
          "icon-image": "bus-stop-icon",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.28, 12, 0.36, 15, 0.46],
          "icon-allow-overlap": true,
        },
      });

      map.addLayer({
        id: "bus-terminal-layer",
        type: "symbol",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "bus_terminal"],
        layout: {
          "icon-image": "bus-terminal-icon",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.34, 12, 0.44, 15, 0.54],
          "icon-allow-overlap": true,
        },
      });

      map.addLayer({
        id: "metro-station-layer",
        type: "circle",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "metro_station"],
        paint: {
          "circle-radius": 5.4,
          "circle-color": "#e11d48",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.6,
          "circle-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "train-station-layer",
        type: "circle",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "train_station"],
        paint: {
          "circle-radius": 5.6,
          "circle-color": "#0f766e",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.6,
          "circle-opacity": 0.97,
        },
      });

      map.addLayer({
        id: "transport-candidate-layer",
        type: "circle",
        source: TRANSPORT_CANDIDATES_SOURCE_ID,
        paint: {
          "circle-radius": ["case", ["boolean", ["get", "selected"], false], 8, 5],
          "circle-color": ["case", ["boolean", ["get", "selected"], false], "#845ef7", "#64748b"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.92,
        },
      });

      map.addLayer({
        id: "zones-runtime-fill-layer",
        type: "fill",
        source: ZONES_SOURCE_ID,
        paint: {
          "fill-color": ["case", ["boolean", ["get", "selected"], false], "#9775fa", "#94a3b8"],
          "fill-opacity": ["case", ["boolean", ["get", "selected"], false], 0.28, 0.12],
        },
      });

      map.addLayer({
        id: "zones-runtime-outline-layer",
        type: "line",
        source: ZONES_SOURCE_ID,
        paint: {
          "line-color": ["case", ["boolean", ["get", "selected"], false], "#845ef7", "#94a3b8"],
          "line-width": ["case", ["boolean", ["get", "selected"], false], 2.5, 1.4],
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "zones-runtime-label-layer",
        type: "symbol",
        source: ZONES_SOURCE_ID,
        layout: {
          "text-field": ["get", "label"],
          "text-size": 12,
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
        },
        paint: {
          "text-color": "#0f172a",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.2,
        },
      });

      map.addLayer({
        id: "journey-listings-layer",
        type: "circle",
        source: LISTINGS_SOURCE_ID,
        paint: {
          "circle-radius": ["case", ["boolean", ["get", "selected"], false], 8, 5],
          "circle-color": ["case", ["boolean", ["get", "selected"], false], "#5b21b6", "#845ef7"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": ["case", ["boolean", ["get", "selected"], false], 2.2, 1.5],
          "circle-opacity": 0.94,
        },
      });

      const openBusPopup = (
        title: string,
        event: maplibregl.MapLayerMouseEvent,
        fallbackName: string
      ) => {
        const feature = event.features?.[0];
        if (!feature?.properties) return;
        const props = feature.properties as Record<string, unknown>;
        const featureName = typeof props.name === "string" && props.name.trim() ? props.name.trim() : fallbackName;
        const buses = parseBusList(props.bus_list);
        const reportedCount = Number(props.bus_count);
        const busCount = Number.isFinite(reportedCount) && reportedCount > 0 ? reportedCount : buses.length;
        const busCountLabel = busCount > 0 ? String(busCount) : "n/d";

        busPopupRef.current?.remove();

        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "340px" })
          .setLngLat(event.lngLat)
          .setHTML(popupContent(title, featureName, busCountLabel, buses))
          .addTo(map);

        busPopupRef.current = popup;
        popup.on("close", () => {
          if (busPopupRef.current === popup) {
            busPopupRef.current = null;
          }
        });
      };

      map.on("click", "bus-line-layer", (event) => {
        openBusPopup("Linha de ônibus", event, "Linha de ônibus");
      });

      map.on("click", "bus-stop-layer", (event) => {
        openBusPopup("Ponto de ônibus", event, "Ponto de ônibus");
      });

      map.on("click", "bus-terminal-layer", (event) => {
        openBusPopup("Terminal de ônibus", event, "Terminal de ônibus");
      });

      map.on("click", "transport-candidate-layer", (event) => {
        const feature = event.features?.[0];
        const transportId = feature?.properties?.id;
        if (typeof transportId === "string") {
          setSelectedTransportId(transportId);
        }
      });

      map.on("click", "zones-runtime-fill-layer", (event) => {
        const feature = event.features?.[0];
        const zoneId = feature?.properties?.id;
        const fingerprint = feature?.properties?.fingerprint;
        if (typeof zoneId === "string" && typeof fingerprint === "string") {
          setSelectedZone(zoneId, fingerprint);
        }
      });

      map.on("click", "journey-listings-layer", (event) => {
        const feature = event.features?.[0];
        const listingKey = feature?.properties?.listing_key;
        if (typeof listingKey === "string" && listingKey.trim()) {
          setSelectedListingKey(listingKey);
        }
      });

      map.on("click", (event) => {
        if (stepRef.current === 1) {
          setPickedCoord({
            lat: event.lngLat.lat,
            lon: event.lngLat.lng,
            label: "Ponto principal"
          });
        }

        const activePopup = busPopupRef.current;
        if (!activePopup) return;

        const clickedBusFeatures = map.queryRenderedFeatures(event.point, {
          layers: [...BUS_LAYER_LIST],
        });
        if (clickedBusFeatures.length > 0) return;

        const popupElement = activePopup.getElement();
        const targetNode = (event.originalEvent?.target as Node | null) ?? null;
        if (targetNode && popupElement.contains(targetNode)) return;

        activePopup.remove();
        busPopupRef.current = null;
      });

      for (const layerId of BUS_LAYER_LIST) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
        });
      }

      for (const layerId of ["transport-candidate-layer", "zones-runtime-fill-layer", "journey-listings-layer"] as const) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = stepRef.current === 1 ? "crosshair" : "";
        });
      }

      setIsMapReady(true);
    });

    return () => {
      busPopupRef.current?.remove();
      busPopupRef.current = null;
      map.remove();
    };
  }, [setPickedCoord, setSelectedListingKey, setSelectedTransportId, setSelectedZone]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    map.getCanvas().style.cursor = step === 1 ? "crosshair" : "";
  }, [isMapReady, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!pickedCoord) {
      pickedMarkerRef.current?.remove();
      pickedMarkerRef.current = null;
      return;
    }

    if (!pickedMarkerRef.current) {
      const markerElement = document.createElement("div");
      markerElement.className = "flex h-6 w-6 items-center justify-center rounded-full border-2 border-white bg-[#845ef7] shadow-lg";
      markerElement.innerHTML = '<span style="display:block;width:8px;height:8px;border-radius:9999px;background:#ffffff"></span>';
      pickedMarkerRef.current = new maplibregl.Marker({ element: markerElement, anchor: "center" })
        .setLngLat([pickedCoord.lon, pickedCoord.lat])
        .addTo(map);
    } else {
      pickedMarkerRef.current.setLngLat([pickedCoord.lon, pickedCoord.lat]);
    }

    map.easeTo({ center: [pickedCoord.lon, pickedCoord.lat], duration: 600, zoom: Math.max(map.getZoom(), 13) });
  }, [isMapReady, pickedCoord]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const activeMap = map;

    let cancelled = false;

    async function syncTransportCandidates() {
      if (!journeyId || step < 2) {
        setGeoJsonSourceData(activeMap, TRANSPORT_CANDIDATES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const points = await getJourneyTransportPoints(journeyId);
      if (!cancelled) {
        setGeoJsonSourceData(
          activeMap,
          TRANSPORT_CANDIDATES_SOURCE_ID,
          toTransportCandidatesFeatureCollection(points, selectedTransportId)
        );
      }
    }

    void syncTransportCandidates().catch(() => {
      if (!cancelled) {
        setGeoJsonSourceData(activeMap, TRANSPORT_CANDIDATES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [isMapReady, journeyId, selectedTransportId, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const activeMap = map;

    let cancelled = false;

    async function syncZones() {
      if (!journeyId || step < 3) {
        setGeoJsonSourceData(activeMap, ZONES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const response = await getJourneyZonesList(journeyId);
      if (!cancelled) {
        setGeoJsonSourceData(
          activeMap,
          ZONES_SOURCE_ID,
          toZonesFeatureCollection(response.zones, selectedZoneFingerprint)
        );
      }
    }

    void syncZones().catch(() => {
      if (!cancelled) {
        setGeoJsonSourceData(activeMap, ZONES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [isMapReady, journeyId, selectedZoneFingerprint, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!selectedListingKey || step < 6) {
      return;
    }

    const selectedListing = (listingsQuery.data?.listings || []).find((listing) => {
      if (typeof listing.lat !== "number" || typeof listing.lon !== "number") {
        return false;
      }
      return getListingSelectionKey(listing) === selectedListingKey;
    });

    if (!selectedListing || typeof selectedListing.lat !== "number" || typeof selectedListing.lon !== "number") {
      return;
    }

    map.easeTo({ center: [selectedListing.lon, selectedListing.lat], duration: 600, zoom: Math.max(map.getZoom(), 14) });
  }, [isMapReady, listingsQuery.data?.listings, selectedListingKey, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!journeyId || !selectedZoneFingerprint || step < 6 || listingsQuery.error) {
      setGeoJsonSourceData(map, LISTINGS_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      return;
    }

    setGeoJsonSourceData(
      map,
      LISTINGS_SOURCE_ID,
      toListingsFeatureCollection(filteredMapListings as Array<Record<string, unknown>>, selectedListingKey)
    );
  }, [filteredMapListings, isMapReady, journeyId, listingsQuery.error, selectedListingKey, selectedZoneFingerprint, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    map.setLayoutProperty("bus-line-layer", "visibility", layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("bus-line-direction-layer", "visibility", layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("metro-line-layer", "visibility", layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("train-line-layer", "visibility", layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("bus-stop-layer", "visibility", layerVisibility.busStops ? "visible" : "none");
    map.setLayoutProperty("bus-terminal-layer", "visibility", layerVisibility.busStops ? "visible" : "none");
    map.setLayoutProperty("metro-station-layer", "visibility", layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("train-station-layer", "visibility", layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("flood-layer", "visibility", layerVisibility.flood ? "visible" : "none");
    map.setLayoutProperty("green-layer", "visibility", layerVisibility.green ? "visible" : "none");
  }, [isMapReady, layerVisibility]);

  if (mapError) {
    return (
      <main className="flex h-screen w-full items-center justify-center bg-slate-900 text-red-400">
        <p className="text-sm">{mapError}</p>
      </main>
    );
  }

  return (
    <main className="relative h-screen w-full overflow-hidden">
      <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />
      <WizardPanel />
    </main>
  );
}
