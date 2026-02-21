import { useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const defaultPoint = { name: "Trabalho", lat: -23.582013, lon: -46.671344 };

export default function App() {
  const [runId, setRunId] = useState("");
  const [zones, setZones] = useState([]);
  const [selected, setSelected] = useState([]);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [finalListings, setFinalListings] = useState([]);
  const [finalReady, setFinalReady] = useState(false);

  const filteredZones = useMemo(() => {
    if (!query.trim()) return zones;
    return zones.filter((z) => String(z.properties?.zone_uid || "").includes(query.trim()));
  }, [zones, query]);

  const createRun = async () => {
    setMessage("Criando run...");
    const response = await fetch(`${API_BASE}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_points: [defaultPoint],
        params: {
          cache_dir: "data_cache",
          zone_dedupe_m: 50,
          max_streets_per_zone: 2,
          listing_max_pages: 1,
          listing_mode: "rent"
        }
      })
    });
    const data = await response.json();
    setRunId(data.run_id);
    setMessage(`Run criado: ${data.run_id}`);
  };

  const loadZones = async () => {
    if (!runId) return;
    setMessage("Carregando zonas...");
    const response = await fetch(`${API_BASE}/runs/${runId}/zones`);
    const data = await response.json();
    setZones(data.features || []);
    setMessage(`Zonas carregadas: ${(data.features || []).length}`);
  };

  const toggleZone = (zoneUid) => {
    setSelected((prev) =>
      prev.includes(zoneUid) ? prev.filter((x) => x !== zoneUid) : [...prev, zoneUid]
    );
  };

  const selectZones = async () => {
    if (!runId || selected.length === 0) return;
    const response = await fetch(`${API_BASE}/runs/${runId}/zones/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zone_uids: selected })
    });
    const data = await response.json();
    setMessage(data.message || "Zonas selecionadas");
  };

  const detailSelected = async () => {
    if (!runId || selected.length === 0) return;
    setMessage("Gerando detalhes de zona...");
    for (const zoneUid of selected) {
      await fetch(`${API_BASE}/runs/${runId}/zones/${zoneUid}/detail`, { method: "POST" });
    }
    setMessage("Detalhes de zonas gerados");
  };

  const scrapeSelected = async () => {
    if (!runId || selected.length === 0) return;
    setMessage("Executando scraping por ruas...");
    for (const zoneUid of selected) {
      await fetch(`${API_BASE}/runs/${runId}/zones/${zoneUid}/listings`, { method: "POST" });
    }
    setMessage("Scraping concluído");
  };

  const finalize = async () => {
    if (!runId) return;
    setMessage("Gerando output final...");
    await fetch(`${API_BASE}/runs/${runId}/finalize`, { method: "POST" });
    const response = await fetch(`${API_BASE}/runs/${runId}/final/listings`);
    const geojson = await response.json();
    const items = (geojson.features || []).map((f) => ({
      ...f.properties,
      lon: f.geometry?.coordinates?.[0],
      lat: f.geometry?.coordinates?.[1]
    }));
    setFinalListings(items);
    setFinalReady(true);
    setMessage(`Output final pronto: ${items.length} imóveis`);
  };

  const mapPoints = useMemo(() => {
    const points = finalListings
      .filter((x) => Number.isFinite(x.lon) && Number.isFinite(x.lat))
      .map((x) => ({ lon: Number(x.lon), lat: Number(x.lat), score: Number(x.score_listing_v1 || 0) }));
    if (!points.length) return [];
    const minLon = Math.min(...points.map((p) => p.lon));
    const maxLon = Math.max(...points.map((p) => p.lon));
    const minLat = Math.min(...points.map((p) => p.lat));
    const maxLat = Math.max(...points.map((p) => p.lat));
    return points.map((p) => ({
      x: 20 + ((p.lon - minLon) / Math.max(1e-9, maxLon - minLon)) * 460,
      y: 280 - ((p.lat - minLat) / Math.max(1e-9, maxLat - minLat)) * 260,
      score: p.score
    }));
  }, [finalListings]);

  return (
    <main className="page">
      <h1>Imovel Ideal</h1>

      <section className="toolbar">
        <button onClick={createRun}>1) Criar Run</button>
        <button onClick={loadZones} disabled={!runId}>2) Carregar Zonas</button>
        <button onClick={selectZones} disabled={!selected.length}>3) Selecionar Zonas</button>
        <button onClick={detailSelected} disabled={!selected.length}>4) Detalhar Zonas</button>
        <button onClick={scrapeSelected} disabled={!selected.length}>5) Buscar Imóveis</button>
        <button onClick={finalize} disabled={!runId}>6) Finalizar</button>
      </section>

      <p className="status">{message}</p>
      {runId ? <p className="run">run_id: {runId}</p> : null}

      <section className="zones">
        <div className="zones-head">
          <h2>Zonas</h2>
          <input
            placeholder="Filtrar zone_uid"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <ul>
          {filteredZones.map((zone) => {
            const props = zone.properties || {};
            const uid = props.zone_uid;
            return (
              <li key={uid}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(uid)}
                    onChange={() => toggleZone(uid)}
                  />
                  <strong>{uid}</strong> | score: {Number(props.score || 0).toFixed(3)} | time_agg: {props.time_agg}
                </label>
                <div className="polygon">polígono: {zone.geometry?.type}</div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="listings">
        <h2>Imóveis finais</h2>
        {finalReady ? (
          <div className="exports">
            <a href={`${API_BASE}/runs/${runId}/final/listings`} target="_blank" rel="noreferrer">Export GeoJSON</a>
            <a href={`${API_BASE}/runs/${runId}/final/listings.csv`} target="_blank" rel="noreferrer">Export CSV</a>
            <a href={`${API_BASE}/runs/${runId}/final/listings.json`} target="_blank" rel="noreferrer">Export JSON</a>
          </div>
        ) : null}

        {mapPoints.length ? (
          <div className="mini-map">
            <svg viewBox="0 0 500 300" role="img" aria-label="Mapa simplificado dos imóveis">
              <rect x="0" y="0" width="500" height="300" fill="#f4f7ff" />
              {mapPoints.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r={4} fill={p.score > 0.6 ? "#2463eb" : "#6f8ddb"} />
              ))}
            </svg>
          </div>
        ) : null}

        <div className="cards">
          {finalListings.map((item, idx) => (
            <article className="card" key={`${item.zone_uid}-${idx}`}>
              <h3>{item.title || item.address || "Imóvel"}</h3>
              <p>Preço: {item.price ?? "n/d"}</p>
              <p>Score: {Number(item.score_listing_v1 || 0).toFixed(3)}</p>
              <p>Dist. transporte: {item.distance_transport_m ? Math.round(item.distance_transport_m) : "n/d"} m</p>
              <p>Dist. POI: {item.distance_poi_m ? Math.round(item.distance_poi_m) : "n/d"} m</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
