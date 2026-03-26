"""Reescreve FindIdealApp.tsx com versão limpa (apenas mapa + camadas)."""
import pathlib

TARGET = pathlib.Path(r"c:\Users\iagoo\PESSOAL\projetos\onde_morar\principal\apps\web\src\features\app\FindIdealApp.tsx")

CLEAN = r'''import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { API_BASE } from "../../api/client";

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_API_KEY || (import.meta.env.MODE === "test" ? "test-maptiler-key" : "");

const mapTilerStyleUrl = (key: string) =>
  `https://api.maptiler.com/maps/bright-v2/style.json?key=${encodeURIComponent(key)}`;

const apiTileUrl = (path: string) => `${API_BASE}${path}`;

export function FindIdealApp() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<Record<string, boolean>>({
    routes: true,
    metro: true,
    train: true,
    busStops: true,
    flood: false,
    green: false,
  });

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
        type: "circle",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["match", ["get", "kind"], ["bus_stop", "bus_terminal"], true, false],
        paint: {
          "circle-radius": ["case", ["==", ["get", "kind"], "bus_terminal"], 5.8, 4.2],
          "circle-color": ["case", ["==", ["get", "kind"], "bus_terminal"], "#f97316", "#845ef7"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.95,
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

      setIsMapReady(true);
    });

    return () => {
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    map.setLayoutProperty("bus-line-layer", "visibility", layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("metro-line-layer", "visibility", layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("train-line-layer", "visibility", layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("bus-stop-layer", "visibility", layerVisibility.busStops ? "visible" : "none");
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
    </main>
  );
}
'''

TARGET.write_text(CLEAN, encoding="utf-8")
print(f"✅ Wrote {len(CLEAN.splitlines())} lines to {TARGET}")
