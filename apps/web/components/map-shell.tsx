"use client";

import { useEffect, useRef } from "react";
import maplibregl, { LngLatLike, Map } from "maplibre-gl";

type Point = {
  lat: number;
  lon: number;
  label: string;
};

type MapShellProps = {
  primaryPoint: Point | null;
  secondaryPoint: Point | null;
  activePointTarget: "primary" | "secondary";
  onPickPoint: (target: "primary" | "secondary", coords: { lat: number; lon: number }) => void;
};

const DEFAULT_CENTER: LngLatLike = [-46.633308, -23.55052];

export function MapShell({ primaryPoint, secondaryPoint, activePointTarget, onPickPoint }: MapShellProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const primaryMarkerRef = useRef<maplibregl.Marker | null>(null);
  const secondaryMarkerRef = useRef<maplibregl.Marker | null>(null);
  const activeTargetRef = useRef(activePointTarget);
  const maptilerKey = process.env.NEXT_PUBLIC_MAPTILER_API_KEY ?? "";

  useEffect(() => {
    activeTargetRef.current = activePointTarget;
  }, [activePointTarget]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !maptilerKey) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: `https://api.maptiler.com/maps/streets-v2/style.json?key=${maptilerKey}`,
      center: DEFAULT_CENTER,
      zoom: 10.6,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.on("click", (event) => {
      onPickPoint(activeTargetRef.current, {
        lat: Number(event.lngLat.lat.toFixed(6)),
        lon: Number(event.lngLat.lng.toFixed(6)),
      });
    });

    mapRef.current = map;

    return () => {
      secondaryMarkerRef.current?.remove();
      primaryMarkerRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, [maptilerKey, onPickPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    const upsertMarker = (
      markerRef: React.MutableRefObject<maplibregl.Marker | null>,
      point: Point | null,
      color: string,
    ) => {
      if (!point) {
        markerRef.current?.remove();
        markerRef.current = null;
        return;
      }

      if (!markerRef.current) {
        markerRef.current = new maplibregl.Marker({ color }).addTo(map);
      }

      markerRef.current
        .setLngLat([point.lon, point.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setHTML(
            `<strong>${point.label}</strong><br/>Lat ${point.lat.toFixed(5)} · Lon ${point.lon.toFixed(5)}`,
          ),
        );
    };

    upsertMarker(primaryMarkerRef, primaryPoint, "#145c52");
    upsertMarker(secondaryMarkerRef, secondaryPoint, "#c47e23");

    const visiblePoints = [primaryPoint, secondaryPoint].filter(Boolean) as Point[];
    if (visiblePoints.length === 1) {
      map.easeTo({ center: [visiblePoints[0].lon, visiblePoints[0].lat], zoom: 12.8, duration: 700 });
    }
    if (visiblePoints.length === 2) {
      const bounds = new maplibregl.LngLatBounds();
      for (const point of visiblePoints) {
        bounds.extend([point.lon, point.lat]);
      }
      map.fitBounds(bounds, { padding: 100, duration: 900 });
    }
  }, [primaryPoint, secondaryPoint]);

  if (!maptilerKey) {
    return (
      <div className="mapFallback">
        <div>
          <p className="mapEyebrow">Mapa indisponível</p>
          <h3>Defina NEXT_PUBLIC_MAPTILER_API_KEY para ativar o MapLibre.</h3>
          <p>
            O formulário continua funcional com coordenadas manuais. Quando a chave estiver presente, o clique no
            mapa passa a preencher os pontos automaticamente.
          </p>
        </div>
      </div>
    );
  }

  return <div className="mapCanvas" ref={containerRef} aria-label="Mapa interativo para seleção de pontos" />;
}