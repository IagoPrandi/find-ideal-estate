import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

type LayerKey = "bus" | "train" | "flood" | "green" | "pois";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const STEPS = [
  { id: 1, label: "Referências" },
  { id: 2, label: "Zonas" },
  { id: 3, label: "Imóveis" }
] as const;

const LAYER_INFO: Record<LayerKey, { label: string; color: string }> = {
  bus: { label: "Rotas de ônibus", color: "#2563eb" },
  train: { label: "Rotas de trilhos", color: "#0f766e" },
  flood: { label: "Alagamento", color: "#7c3aed" },
  green: { label: "Área verde", color: "#16a34a" },
  pois: { label: "POIs", color: "#d97706" }
};

export default function App() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markerRef = useRef<mapboxgl.Marker | null>(null);

  const [searchValue, setSearchValue] = useState("");
  const [isPanelMinimized, setIsPanelMinimized] = useState(false);
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [viewport, setViewport] = useState({ lat: -23.55052, lon: -46.633308, zoom: 10.7 });
  const [layerVisibility, setLayerVisibility] = useState<Record<LayerKey, boolean>>({
    bus: true,
    train: true,
    flood: false,
    green: false,
    pois: false
  });

  const initialViewport = useRef(viewport);

  useEffect(() => {
    if (!mapContainerRef.current) {
      return;
    }

    if (!MAPBOX_TOKEN) {
      setMapError("Defina VITE_MAPBOX_ACCESS_TOKEN no .env do frontend para renderizar o mapa.");
      return;
    }

    mapboxgl.accessToken = MAPBOX_TOKEN;
    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/light-v11",
      center: [initialViewport.current.lon, initialViewport.current.lat],
      zoom: initialViewport.current.zoom,
      pitchWithRotate: false,
      dragRotate: false
    });

    mapRef.current = map;

    map.on("load", () => {
      map.addSource("transport-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: [
                  [-46.705, -23.56],
                  [-46.64, -23.54],
                  [-46.58, -23.5]
                ]
              },
              properties: { mode: "bus" }
            },
            {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: [
                  [-46.69, -23.62],
                  [-46.63, -23.58],
                  [-46.57, -23.55]
                ]
              },
              properties: { mode: "train" }
            }
          ]
        }
      });

      map.addSource("env-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [-46.67, -23.57],
                    [-46.64, -23.57],
                    [-46.64, -23.54],
                    [-46.67, -23.54],
                    [-46.67, -23.57]
                  ]
                ]
              },
              properties: { kind: "flood" }
            },
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [-46.62, -23.55],
                    [-46.59, -23.55],
                    [-46.59, -23.52],
                    [-46.62, -23.52],
                    [-46.62, -23.55]
                  ]
                ]
              },
              properties: { kind: "green" }
            }
          ]
        }
      });

      map.addSource("poi-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [-46.621, -23.534] },
              properties: { name: "POI Exemplo" }
            }
          ]
        }
      });

      map.addLayer({
        id: "bus-layer",
        type: "line",
        source: "transport-demo",
        filter: ["==", ["get", "mode"], "bus"],
        paint: { "line-color": "#2563eb", "line-width": 4, "line-dasharray": [1.5, 1.5] }
      });
      map.addLayer({
        id: "train-layer",
        type: "line",
        source: "transport-demo",
        filter: ["==", ["get", "mode"], "train"],
        paint: { "line-color": "#0f766e", "line-width": 4 }
      });
      map.addLayer({
        id: "flood-layer",
        type: "fill",
        source: "env-demo",
        filter: ["==", ["get", "kind"], "flood"],
        paint: { "fill-color": "#7c3aed", "fill-opacity": 0.28 }
      });
      map.addLayer({
        id: "green-layer",
        type: "fill",
        source: "env-demo",
        filter: ["==", ["get", "kind"], "green"],
        paint: { "fill-color": "#16a34a", "fill-opacity": 0.28 }
      });
      map.addLayer({
        id: "poi-layer",
        type: "circle",
        source: "poi-demo",
        paint: {
          "circle-radius": 7,
          "circle-color": "#d97706",
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2
        }
      });

      map.on("moveend", () => {
        const center = map.getCenter();
        setViewport({ lat: center.lat, lon: center.lng, zoom: map.getZoom() });
      });

      map.on("click", (event) => {
        const { lng, lat } = event.lngLat;
        markerRef.current?.remove();
        markerRef.current = new mapboxgl.Marker({ color: "#2563eb" }).setLngLat([lng, lat]).addTo(map);
      });

      setIsMapReady(true);
    });

    map.on("error", () => {
      setMapError("Falha ao carregar mapa. Verifique token, rede e estilo configurado.");
    });

    return () => {
      markerRef.current?.remove();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const visibility = (value: boolean) => (value ? "visible" : "none");
    map.setLayoutProperty("bus-layer", "visibility", visibility(layerVisibility.bus));
    map.setLayoutProperty("train-layer", "visibility", visibility(layerVisibility.train));
    map.setLayoutProperty("flood-layer", "visibility", visibility(layerVisibility.flood));
    map.setLayoutProperty("green-layer", "visibility", visibility(layerVisibility.green));
    map.setLayoutProperty("poi-layer", "visibility", visibility(layerVisibility.pois));
  }, [isMapReady, layerVisibility]);

  const activeLegendItems = useMemo(
    () =>
      (Object.keys(layerVisibility) as LayerKey[])
        .filter((key) => layerVisibility[key])
        .map((key) => ({ key, ...LAYER_INFO[key] })),
    [layerVisibility]
  );

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const map = mapRef.current;
    if (!map || !searchValue.trim() || !MAPBOX_TOKEN) {
      return;
    }

    const encodedQuery = encodeURIComponent(searchValue.trim());
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodedQuery}.json?access_token=${MAPBOX_TOKEN}&limit=1&language=pt`;
    const response = await fetch(url);
    const data = (await response.json()) as {
      features?: Array<{ center?: [number, number] }>;
    };
    const center = data.features?.[0]?.center;
    if (!center) {
      return;
    }

    map.flyTo({ center, zoom: 13, duration: 900 });
    markerRef.current?.remove();
    markerRef.current = new mapboxgl.Marker({ color: "#2563eb" }).setLngLat(center).addTo(map);
  };

  const toggleLayer = (key: LayerKey) => {
    setLayerVisibility((current) => ({ ...current, [key]: !current[key] }));
  };

  const zoomIn = () => mapRef.current?.zoomIn({ duration: 180 });
  const zoomOut = () => mapRef.current?.zoomOut({ duration: 180 });

  return (
    <main className="h-full w-full bg-bg text-text">
      <div className="relative flex h-full w-full overflow-hidden">
        <section className="relative h-full min-w-0 flex-1">
          <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />

          <div className="pointer-events-none absolute inset-0">
            <div className="pointer-events-auto absolute left-4 top-4 z-20 w-[min(460px,calc(100%-2rem))] rounded-panel border border-border bg-panel/95 p-3 shadow-panel backdrop-blur-sm">
              <form className="flex gap-2" onSubmit={handleSearch}>
                <label htmlFor="map-search" className="sr-only">
                  Buscar endereço
                </label>
                <input
                  id="map-search"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                  placeholder="Buscar endereço ou bairro"
                  className="w-full rounded-xl border border-border px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25"
                />
                <button
                  type="submit"
                  className="rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-white transition hover:brightness-105"
                >
                  Buscar
                </button>
              </form>
              <div className="mt-2 flex flex-wrap gap-2">
                {STEPS.map((step) => (
                  <span
                    key={step.id}
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      step.id === 1
                        ? "bg-primary text-white"
                        : "border border-border bg-white text-muted"
                    }`}
                  >
                    {step.id}. {step.label}
                  </span>
                ))}
              </div>
            </div>

            <div className="pointer-events-auto absolute right-4 top-4 z-20 flex flex-col items-end gap-2">
              <button
                type="button"
                onClick={() => setIsLayerMenuOpen((open) => !open)}
                className="rounded-xl border border-border bg-panel px-3 py-2 text-sm font-medium shadow-panel"
              >
                Camadas
              </button>
              {isLayerMenuOpen ? (
                <div className="w-56 rounded-panel border border-border bg-panel p-3 shadow-panel">
                  {(Object.keys(LAYER_INFO) as LayerKey[]).map((key) => (
                    <label key={key} className="mb-2 flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={layerVisibility[key]}
                        onChange={() => toggleLayer(key)}
                        className="h-4 w-4 accent-primary"
                      />
                      <span>{LAYER_INFO[key].label}</span>
                    </label>
                  ))}
                </div>
              ) : null}

              <div className="flex overflow-hidden rounded-xl border border-border bg-panel shadow-panel">
                <button type="button" onClick={zoomIn} className="px-3 py-2 text-lg">
                  +
                </button>
                <button type="button" onClick={zoomOut} className="border-l border-border px-3 py-2 text-lg">
                  −
                </button>
              </div>

              <button
                type="button"
                onClick={() => setIsHelpOpen(true)}
                className="rounded-xl border border-border bg-panel px-3 py-2 text-sm font-medium shadow-panel"
              >
                Ajuda
              </button>
            </div>

            <div className="pointer-events-auto absolute bottom-4 left-4 z-20 rounded-panel border border-border bg-panel/95 p-3 shadow-panel backdrop-blur-sm">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Legenda</p>
              {activeLegendItems.length ? (
                <ul className="space-y-1">
                  {activeLegendItems.map((item) => (
                    <li key={item.key} className="flex items-center gap-2 text-xs text-text">
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: item.color }}
                        aria-hidden="true"
                      />
                      {item.label}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted">Ative camadas para visualizar a legenda.</p>
              )}
            </div>

            {mapError ? (
              <div className="pointer-events-none absolute inset-0 z-30 grid place-items-center bg-slate-950/35 p-6">
                <div className="pointer-events-auto max-w-md rounded-panel border border-danger/30 bg-panel p-4 text-sm text-danger shadow-panel">
                  {mapError}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <aside
          className={`relative h-full border-l border-border bg-panel shadow-panel transition-all duration-300 ${
            isPanelMinimized ? "w-16" : "w-[400px]"
          }`}
          aria-label="Painel lateral"
        >
          <button
            type="button"
            onClick={() => setIsPanelMinimized((value) => !value)}
            className="absolute left-2 top-2 z-20 rounded-lg border border-border bg-white px-2 py-1 text-xs font-semibold text-muted"
            aria-expanded={!isPanelMinimized}
          >
            {isPanelMinimized ? "Abrir" : "Minimizar"}
          </button>

          {!isPanelMinimized ? (
            <div className="panel-scroll h-full overflow-y-auto px-5 pb-6 pt-12">
              <h1 className="text-xl font-bold">Imóvel Ideal</h1>
              <p className="mt-1 text-sm text-muted">Milestone FE0 — layout base e chrome do mapa.</p>

              <section className="mt-6 rounded-panel border border-border p-4">
                <h2 className="text-sm font-semibold">Checklist FE0</h2>
                <ul className="mt-3 space-y-2 text-sm text-muted">
                  <li>• Vite + React + TypeScript com lint/format configurados.</li>
                  <li>• Tailwind com tokens de cor/spacing/tipografia.</li>
                  <li>• Mapa com Mapbox GL JS e token por variável de ambiente.</li>
                  <li>• Layout split-screen com painel fixo e minimização.</li>
                  <li>• Busca, stepper, zoom, camadas, legenda e ajuda no mapa.</li>
                </ul>
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <p className="font-semibold">Status do ambiente</p>
                <p className="mt-2 text-muted">API base: {API_BASE}</p>
                <p className="text-muted">
                  Mapa: {isMapReady ? "carregado" : "inicializando"} | Zoom: {viewport.zoom.toFixed(2)}
                </p>
                <p className="text-muted">
                  Centro: {viewport.lat.toFixed(5)}, {viewport.lon.toFixed(5)}
                </p>
              </section>
            </div>
          ) : (
            <div className="grid h-full place-items-center pt-8">
              <span className="-rotate-90 text-xs font-semibold tracking-[0.18em] text-muted">PAINEL</span>
            </div>
          )}
        </aside>
      </div>

      {isHelpOpen ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/45 p-4">
          <div className="w-full max-w-lg rounded-panel border border-border bg-panel p-5 shadow-panel">
            <h2 className="text-lg font-semibold">Ajuda — FE0</h2>
            <p className="mt-2 text-sm text-muted">
              Este passo entrega a base visual do frontend: mapa funcional, painel lateral fixo, controles
              globais e tokens de design para consistência.
            </p>
            <p className="mt-3 text-sm text-muted">
              Próximos passos (FE1+): conexão com criação de run, zonas, seleção e imóveis finais.
            </p>
            <div className="mt-4 text-right">
              <button
                type="button"
                onClick={() => setIsHelpOpen(false)}
                className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}