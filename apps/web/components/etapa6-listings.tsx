"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Etapa6Props = {
  journeyId: string;
  zoneFingerprint: string;
  searchType: "rent" | "buy";
  initialListings?: ListingCard[];
  cacheAgeHours?: number;
  freshnessStatus?: string;
  jobId?: string;
};

type ListingCard = {
  listing_ad_id: string;
  property_id: string;
  platform: string;
  external_id: string;
  external_url: string;
  address_display: string;
  neighborhood?: string;
  area_m2?: number;
  bedrooms?: number;
  bathrooms?: number;
  parking_spots?: number;
  current_best_price?: number;
  second_best_price?: number;
  price_currency: string;
  usage_type: string;
  property_type?: string;
  thumbnail_url?: string;
  duplication_badge?: boolean;
  lat?: number;
  lon?: number;
  scraped_at?: string;
};

type FilterState = {
  minPrice: number;
  maxPrice: number;
  minArea: number;
  maxArea: number;
  platforms: string[];
  sortBy: "price_asc" | "price_desc" | "area_desc" | "recent";
};

const FREE_PLATFORMS = ["quintoandar", "zapimoveis"];
const ALL_PLATFORMS = ["quintoandar", "zapimoveis", "vivareal"];

function formatPrice(value: number | undefined, currency: string): string {
  if (value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: currency === "BRL" ? "BRL" : "BRL",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatAreaM2(value: number | undefined): string {
  if (value === undefined) return "—";
  return `${value} m²`;
}

function platformLabel(platform: string): string {
  const map: Record<string, string> = {
    quintoandar: "QuintoAndar",
    zapimoveis: "ZAP Imóveis",
    vivareal: "Viva Real",
  };
  return map[platform] ?? platform;
}

function freshnessLabel(ageHours: number | undefined): string {
  if (ageHours === undefined) return "Dados recém-carregados";
  if (ageHours < 1) return "Dados de menos de 1h atrás";
  if (ageHours < 24) return `Dados de ${Math.floor(ageHours)}h atrás`;
  const days = Math.floor(ageHours / 24);
  return `Dados de ${days}d atrás`;
}

export function Etapa6Listings({
  journeyId,
  zoneFingerprint,
  searchType,
  initialListings,
  cacheAgeHours,
  freshnessStatus,
  jobId: _jobId,
}: Etapa6Props) {
  const [listings, setListings] = useState<ListingCard[]>(initialListings ?? []);
  const [isLoading, setIsLoading] = useState(!initialListings);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    minPrice: 0,
    maxPrice: 0,
    minArea: 0,
    maxArea: 0,
    platforms: [...FREE_PLATFORMS],
    sortBy: "price_asc",
  });
  const [priceRange, setPriceRange] = useState({ min: 0, max: 0 });
  const [areaRange, setAreaRange] = useState({ min: 0, max: 0 });
  const hasFetchedRef = useRef(false);

  const fetchListings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        search_type: searchType === "rent" ? "rent" : "sale",
        usage_type: "residential",
        platforms: filters.platforms.join(","),
      });
      const res = await fetch(
        `/api/journeys/${journeyId}/zones/${zoneFingerprint}/listings?${params.toString()}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error("Falha ao carregar imóveis");
      const data = (await res.json()) as { listings: ListingCard[] };
      setListings(data.listings);

      // Compute dynamic filter ranges from data
      const prices = data.listings.map((l) => l.current_best_price).filter(Boolean) as number[];
      const areas = data.listings.map((l) => l.area_m2).filter(Boolean) as number[];
      if (prices.length > 0) {
        const minP = Math.min(...prices);
        const maxP = Math.max(...prices);
        setPriceRange({ min: minP, max: maxP });
        setFilters((prev) => ({ ...prev, minPrice: minP, maxPrice: maxP }));
      }
      if (areas.length > 0) {
        const minA = Math.min(...areas);
        const maxA = Math.max(...areas);
        setAreaRange({ min: minA, max: maxA });
        setFilters((prev) => ({ ...prev, minArea: minA, maxArea: maxA }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar imóveis");
    } finally {
      setIsLoading(false);
    }
  }, [journeyId, zoneFingerprint, searchType, filters.platforms]);

  useEffect(() => {
    if (initialListings && initialListings.length > 0 && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      const prices = initialListings.map((l) => l.current_best_price).filter(Boolean) as number[];
      const areas = initialListings.map((l) => l.area_m2).filter(Boolean) as number[];
      if (prices.length > 0) {
        const minP = Math.min(...prices);
        const maxP = Math.max(...prices);
        setPriceRange({ min: minP, max: maxP });
        setFilters((prev) => ({ ...prev, minPrice: minP, maxPrice: maxP }));
      }
      if (areas.length > 0) {
        const minA = Math.min(...areas);
        const maxA = Math.max(...areas);
        setAreaRange({ min: minA, max: maxA });
        setFilters((prev) => ({ ...prev, minArea: minA, maxArea: maxA }));
      }
      return;
    }
    if (!hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchListings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const togglePlatform = (platform: string) => {
    setFilters((prev) => {
      const current = prev.platforms;
      if (current.includes(platform)) {
        if (current.length === 1) return prev; // must keep at least one
        return { ...prev, platforms: current.filter((p) => p !== platform) };
      }
      return { ...prev, platforms: [...current, platform] };
    });
  };

  const filteredListings = listings
    .filter((l) => {
      if (!filters.platforms.includes(l.platform)) return false;
      if (filters.maxPrice > 0 && l.current_best_price !== undefined) {
        if (l.current_best_price < filters.minPrice || l.current_best_price > filters.maxPrice) {
          return false;
        }
      }
      if (filters.maxArea > 0 && l.area_m2 !== undefined) {
        if (l.area_m2 < filters.minArea || l.area_m2 > filters.maxArea) {
          return false;
        }
      }
      return true;
    })
    .sort((a, b) => {
      switch (filters.sortBy) {
        case "price_asc":
          return (a.current_best_price ?? Infinity) - (b.current_best_price ?? Infinity);
        case "price_desc":
          return (b.current_best_price ?? 0) - (a.current_best_price ?? 0);
        case "area_desc":
          return (b.area_m2 ?? 0) - (a.area_m2 ?? 0);
        case "recent":
          return (b.scraped_at ?? "") > (a.scraped_at ?? "") ? 1 : -1;
        default:
          return 0;
      }
    });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 600 }}>
            Imóveis disponíveis
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: "0.75rem", color: "var(--muted, #888)" }}>
            {freshnessLabel(cacheAgeHours)}
            {freshnessStatus === "stale" && " · cache desatualizado, atualizando em segundo plano"}
          </p>
        </div>
        <button
          type="button"
          style={{
            padding: "6px 14px",
            fontSize: "0.8rem",
            borderRadius: "6px",
            border: "1px solid var(--line, #ddd)",
            background: "transparent",
            cursor: "pointer",
          }}
          onClick={() => {
            hasFetchedRef.current = false;
            fetchListings();
          }}
        >
          Atualizar
        </button>
      </div>

      {/* Filters */}
      <div
        style={{
          padding: "12px 16px",
          border: "1px solid var(--line, #e5e5e5)",
          borderRadius: "10px",
          display: "flex",
          gap: "24px",
          flexWrap: "wrap",
          alignItems: "flex-end",
        }}
      >
        {/* Platform toggles */}
        <div>
          <p style={{ margin: "0 0 6px", fontSize: "0.7rem", color: "var(--muted, #888)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Plataformas
          </p>
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {ALL_PLATFORMS.map((p) => {
              const isPro = !FREE_PLATFORMS.includes(p);
              const isActive = filters.platforms.includes(p);
              return (
                <button
                  key={p}
                  type="button"
                  disabled={isPro}
                  onClick={() => !isPro && togglePlatform(p)}
                  title={isPro ? "Disponível no plano Pro" : undefined}
                  style={{
                    padding: "4px 10px",
                    fontSize: "0.75rem",
                    borderRadius: "9999px",
                    border: "1px solid var(--line, #ddd)",
                    background: isActive && !isPro ? "var(--accent, #0070f3)" : "transparent",
                    color: isActive && !isPro ? "#fff" : isPro ? "var(--muted, #aaa)" : "inherit",
                    cursor: isPro ? "not-allowed" : "pointer",
                    opacity: isPro ? 0.6 : 1,
                  }}
                >
                  {platformLabel(p)}
                  {isPro && " 🔒"}
                </button>
              );
            })}
          </div>
        </div>

        {/* Price range */}
        {priceRange.max > 0 && (
          <div>
            <p style={{ margin: "0 0 6px", fontSize: "0.7rem", color: "var(--muted, #888)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Preço (R$)
            </p>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "0.8rem" }}>
              <input
                type="number"
                value={filters.minPrice}
                min={priceRange.min}
                max={filters.maxPrice}
                step={100}
                onChange={(e) => setFilters((prev) => ({ ...prev, minPrice: Number(e.target.value) }))}
                style={{ width: "80px", padding: "3px 6px", border: "1px solid var(--line, #ddd)", borderRadius: "4px" }}
              />
              <span>–</span>
              <input
                type="number"
                value={filters.maxPrice}
                min={filters.minPrice}
                max={priceRange.max}
                step={100}
                onChange={(e) => setFilters((prev) => ({ ...prev, maxPrice: Number(e.target.value) }))}
                style={{ width: "80px", padding: "3px 6px", border: "1px solid var(--line, #ddd)", borderRadius: "4px" }}
              />
            </div>
          </div>
        )}

        {/* Area range */}
        {areaRange.max > 0 && (
          <div>
            <p style={{ margin: "0 0 6px", fontSize: "0.7rem", color: "var(--muted, #888)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Área (m²)
            </p>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "0.8rem" }}>
              <input
                type="number"
                value={filters.minArea}
                min={areaRange.min}
                max={filters.maxArea}
                step={5}
                onChange={(e) => setFilters((prev) => ({ ...prev, minArea: Number(e.target.value) }))}
                style={{ width: "72px", padding: "3px 6px", border: "1px solid var(--line, #ddd)", borderRadius: "4px" }}
              />
              <span>–</span>
              <input
                type="number"
                value={filters.maxArea}
                min={filters.minArea}
                max={areaRange.max}
                step={5}
                onChange={(e) => setFilters((prev) => ({ ...prev, maxArea: Number(e.target.value) }))}
                style={{ width: "72px", padding: "3px 6px", border: "1px solid var(--line, #ddd)", borderRadius: "4px" }}
              />
            </div>
          </div>
        )}

        {/* Sort */}
        <div>
          <p style={{ margin: "0 0 6px", fontSize: "0.7rem", color: "var(--muted, #888)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Ordenar por
          </p>
          <select
            value={filters.sortBy}
            onChange={(e) => setFilters((prev) => ({ ...prev, sortBy: e.target.value as FilterState["sortBy"] }))}
            style={{ padding: "4px 8px", fontSize: "0.8rem", border: "1px solid var(--line, #ddd)", borderRadius: "4px" }}
          >
            <option value="price_asc">Menor preço</option>
            <option value="price_desc">Maior preço</option>
            <option value="area_desc">Maior área</option>
            <option value="recent">Mais recente</option>
          </select>
        </div>
      </div>

      {/* Loading / error */}
      {isLoading && (
        <p style={{ textAlign: "center", color: "var(--muted, #888)", padding: "32px 0" }}>
          Carregando imóveis...
        </p>
      )}
      {!isLoading && error && (
        <p style={{ textAlign: "center", color: "var(--error, #c00)", padding: "16px 0" }}>
          {error}
        </p>
      )}

      {/* Results summary */}
      {!isLoading && !error && (
        <p style={{ fontSize: "0.8rem", color: "var(--muted, #888)" }}>
          {filteredListings.length} imóvel{filteredListings.length !== 1 ? "is" : ""} encontrado{filteredListings.length !== 1 ? "s" : ""}
          {filteredListings.length !== listings.length && ` (de ${listings.length} total)`}
        </p>
      )}

      {/* Cards grid */}
      {!isLoading && !error && filteredListings.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "16px",
          }}
        >
          {filteredListings.map((listing) => (
            <ListingCardItem key={listing.listing_ad_id} listing={listing} />
          ))}
        </div>
      )}

      {!isLoading && !error && filteredListings.length === 0 && listings.length > 0 && (
        <p style={{ textAlign: "center", color: "var(--muted, #888)", padding: "32px 0" }}>
          Nenhum imóvel corresponde aos filtros. Ajuste os critérios acima.
        </p>
      )}

      {!isLoading && !error && listings.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--muted, #888)", padding: "32px 0" }}>
          Nenhum imóvel encontrado para esta zona.
        </p>
      )}
    </div>
  );
}

function ListingCardItem({ listing }: { listing: ListingCard }) {
  const hasSecondPrice =
    listing.second_best_price !== undefined &&
    listing.second_best_price !== listing.current_best_price;

  return (
    <div
      style={{
        border: "1px solid var(--line, #e5e5e5)",
        borderRadius: "10px",
        overflow: "hidden",
        background: "var(--panel, #fff)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Thumbnail */}
      <div
        style={{
          height: "160px",
          background: listing.thumbnail_url ? "transparent" : "var(--bg-subtle, #f5f5f5)",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {listing.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={listing.thumbnail_url}
            alt={listing.address_display}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--muted, #aaa)",
              fontSize: "0.75rem",
            }}
          >
            Sem foto
          </div>
        )}

        {/* Platform badge */}
        <span
          style={{
            position: "absolute",
            top: "8px",
            left: "8px",
            padding: "2px 8px",
            fontSize: "0.65rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            borderRadius: "9999px",
            background: "rgba(0,0,0,0.65)",
            color: "#fff",
          }}
        >
          {platformLabel(listing.platform)}
        </span>

        {/* Duplication badge */}
        {listing.duplication_badge && (
          <span
            style={{
              position: "absolute",
              top: "8px",
              right: "8px",
              padding: "2px 8px",
              fontSize: "0.65rem",
              fontWeight: 600,
              borderRadius: "9999px",
              background: "rgba(255, 165, 0, 0.9)",
              color: "#000",
            }}
            title="Listado em múltiplas plataformas"
          >
            Dup
          </span>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: "6px", flex: 1 }}>
        {/* Price */}
        <div>
          <p style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>
            {formatPrice(listing.current_best_price, listing.price_currency)}
          </p>
          {hasSecondPrice && (
            <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--muted, #888)" }}>
              Também em {formatPrice(listing.second_best_price, listing.price_currency)} em outra plataforma
            </p>
          )}
        </div>

        {/* Address */}
        <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--muted, #666)" }}>
          {listing.address_display}
          {listing.neighborhood && ` · ${listing.neighborhood}`}
        </p>

        {/* Specs row */}
        <div style={{ display: "flex", gap: "10px", fontSize: "0.78rem", color: "var(--muted, #666)" }}>
          {listing.area_m2 !== undefined && <span>{formatAreaM2(listing.area_m2)}</span>}
          {listing.bedrooms !== undefined && (
            <span>{listing.bedrooms} qto{listing.bedrooms !== 1 ? "s" : ""}</span>
          )}
          {listing.bathrooms !== undefined && <span>{listing.bathrooms} ban{listing.bathrooms !== 1 ? "heiros" : "heiro"}</span>}
          {listing.parking_spots !== undefined && listing.parking_spots > 0 && (
            <span>{listing.parking_spots} vaga{listing.parking_spots !== 1 ? "s" : ""}</span>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: "8px", marginTop: "auto", paddingTop: "8px" }}>
          <a
            href={listing.external_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              flex: 1,
              padding: "6px 10px",
              fontSize: "0.78rem",
              fontWeight: 600,
              textAlign: "center",
              borderRadius: "6px",
              background: "var(--accent, #0070f3)",
              color: "#fff",
              textDecoration: "none",
            }}
          >
            Ver anúncio
          </a>
        </div>
      </div>
    </div>
  );
}
