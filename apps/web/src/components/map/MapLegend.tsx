import type { ZoneDetailResponse } from "../../api/schemas";
import type { MapLayerKey } from "../../domain/mapLayers";

type TransportAnchor = {
  id: string;
  name: string;
  kind: string;
  lon: number;
  lat: number;
  zoneUid?: string;
};

type Props = {
  showCard: boolean;
  stopsLoading: boolean;
  layerVisibility: Record<MapLayerKey, boolean>;
  hasRouteData: boolean;
  activeStep: number;
  originalSeedPoint: TransportAnchor | null;
  zoneSeedPoints: TransportAnchor[];
  zoneDownstreamPoints: TransportAnchor[];
  zoneDetailData: ZoneDetailResponse | null;
  zonesCollectionLength: number;
};

export function MapLegend({
  showCard,
  stopsLoading,
  layerVisibility,
  hasRouteData,
  activeStep,
  originalSeedPoint,
  zoneSeedPoints,
  zoneDownstreamPoints,
  zoneDetailData,
  zonesCollectionLength
}: Props) {
  if (!showCard) {
    return null;
  }

  return (
    <div className="pointer-events-auto absolute bottom-6 left-6 z-40 flex flex-col gap-3">
      <div className="flex min-w-[160px] flex-col gap-2.5 rounded-xl border border-slate-200 bg-white/95 p-4 text-xs font-medium text-slate-600 shadow-lg backdrop-blur-md">
        <span className="mb-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">Legenda</span>
        {stopsLoading && layerVisibility.busStops ? <p className="text-slate-500">Carregando paradas...</p> : null}
        {layerVisibility.flood ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded border border-purple-700/30 bg-purple-600/50" /> Risco de Cheia
          </div>
        ) : null}
        {layerVisibility.green ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded border border-green-600/30 bg-green-500/50" /> Área Verde
          </div>
        ) : null}
        {layerVisibility.routes && hasRouteData ? (
          <>
            <div className="flex items-center gap-2">
              <div className="w-4 border-b-2 border-red-500" /> Metrô/Trem
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 border-b-2 border-dashed border-orange-500" /> Ônibus
            </div>
          </>
        ) : null}
        {layerVisibility.busStops ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-blue-600" /> Paradas/estações
          </div>
        ) : null}
        {layerVisibility.busStops && originalSeedPoint ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-red-700" /> Seed original
          </div>
        ) : null}
        {layerVisibility.busStops && zoneSeedPoints.length > 0 ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-orange-600" /> Seeds das zonas
          </div>
        ) : null}
        {layerVisibility.busStops && zoneDownstreamPoints.length > 0 ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-violet-600" /> Downstream das zonas
          </div>
        ) : null}
        {layerVisibility.busStops && zoneDetailData?.seed_transport_point ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-red-600" /> Seed (ponto principal)
          </div>
        ) : null}
        {layerVisibility.busStops && zoneDetailData?.downstream_transport_point ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-violet-600" /> Downstream da zona
          </div>
        ) : null}
        {activeStep === 2 && layerVisibility.transportCandidates ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded-full border border-white bg-orange-600" /> Pontos de transporte (etapa 2)
          </div>
        ) : null}
        {activeStep === 2 && layerVisibility.transportRadius ? (
          <div className="flex items-center gap-2">
            <div className="w-4 border-b-2 border-dashed border-sky-600" /> Raio de busca (etapa 2)
          </div>
        ) : null}
        {layerVisibility.zones && zonesCollectionLength > 0 ? (
          <div className="flex items-center gap-2">
            <div className="h-3.5 w-3.5 rounded border border-pastel-violet-600/50 bg-pastel-violet-500/30" /> Zonas
          </div>
        ) : null}
      </div>
    </div>
  );
}
