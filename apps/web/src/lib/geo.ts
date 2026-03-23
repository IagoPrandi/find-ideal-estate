/** Anel de coordenadas [lon, lat] para desenho de círculo aproximado no mapa (MapLibre GeoJSON). */
export function buildCircleCoordinates(centerLon: number, centerLat: number, radiusM: number): [number, number][][] {
  const earthRadiusM = 6371008.8;
  const latRad = (centerLat * Math.PI) / 180;
  const dLat = (radiusM / earthRadiusM) * (180 / Math.PI);
  const dLon = dLat / Math.max(Math.cos(latRad), 0.000001);

  const ring: [number, number][] = [];
  const steps = 48;
  for (let i = 0; i <= steps; i += 1) {
    const angle = (2 * Math.PI * i) / steps;
    ring.push([centerLon + dLon * Math.cos(angle), centerLat + dLat * Math.sin(angle)]);
  }
  return [ring];
}

export function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const radius = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return radius * c;
}
