export function formatMeters(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/d";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)} km`;
  }
  return `${Math.round(value)} m`;
}

export function formatWalkTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return "n/d";
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `${minutes} min`;
}

export function formatModalTypes(modalTypes: string[]): string {
  if (!modalTypes || modalTypes.length === 0) {
    return "n/d";
  }
  return modalTypes.map((item) => item.toUpperCase()).join(" + ");
}
