const { request } = require("playwright");

const API_BASE = process.env.E2E_API_BASE || "http://localhost:8000";
const POLL_MS = Number(process.env.E2E_POLL_MS || 2000);
const JOB_TIMEOUT_MS = Number(process.env.E2E_JOB_TIMEOUT_MS || 180000);

function log(step, message) {
  const ts = new Date().toISOString();
  console.log(`[${ts}] STEP=${step} ${message}`);
}

async function expectOk(response, context) {
  if (!response.ok()) {
    const body = await response.text();
    throw new Error(`${context} failed: HTTP ${response.status()} body=${body}`);
  }
}

async function getJsonOrThrow(response, context) {
  await expectOk(response, context);
  return response.json();
}

async function waitJobCompleted(api, jobId, step) {
  const started = Date.now();
  while (Date.now() - started < JOB_TIMEOUT_MS) {
    const res = await api.get(`/jobs/${jobId}`);
    const job = await getJsonOrThrow(res, `${step}/job_status`);

    if (job.state === "completed") {
      return job;
    }
    if (job.state === "failed" || job.state === "cancelled" || job.state === "cancelled_partial") {
      throw new Error(`${step} job finished in non-success state=${job.state} error=${job.error_message || "n/a"}`);
    }

    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }

  throw new Error(`${step} timed out after ${JOB_TIMEOUT_MS}ms`);
}

async function createJob(api, journeyId, jobType, step) {
  const res = await api.post("/jobs", {
    data: {
      journey_id: journeyId,
      job_type: jobType,
      current_stage: jobType,
    },
  });
  const job = await getJsonOrThrow(res, `${step}/create_job`);
  log(step, `job_created id=${job.id} type=${job.job_type}`);
  return job;
}

async function main() {
  const api = await request.newContext({ baseURL: API_BASE });
  const evidence = {
    api_base: API_BASE,
    started_at: new Date().toISOString(),
    steps: {},
  };

  try {
    const healthRes = await api.get("/health");
    await expectOk(healthRes, "health_check");

    // Step 1: create journey
    const createJourneyRes = await api.post("/journeys", {
      data: {
        input_snapshot: {
          reference_point: { lat: -23.55052, lon: -46.633308 },
          transport_modal: "transit",
          transport_search_radius_meters: 1800,
          zone_modal: "transit",
          max_time_minutes: 30,
          zone_radius_meters: 1600,
        },
      },
    });
    const journey = await getJsonOrThrow(createJourneyRes, "step1/create_journey");
    const journeyId = journey.id;
    evidence.steps.step1 = { journey_id: journeyId, state: journey.state };
    log("1", `PASS journey_id=${journeyId}`);

    // Step 2: transport search
    const transportJob = await createJob(api, journeyId, "transport_search", "step2");
    const transportDone = await waitJobCompleted(api, transportJob.id, "step2");
    const pointsRes = await api.get(`/journeys/${journeyId}/transport-points`);
    const points = await getJsonOrThrow(pointsRes, "step2/transport_points");
    if (!Array.isArray(points) || points.length === 0) {
      throw new Error("step2 expected at least one transport point");
    }
    evidence.steps.step2 = {
      job_id: transportDone.id,
      transport_points: points.length,
      first_transport_point_id: points[0].id,
    };
    log("2", `PASS transport_points=${points.length}`);

    // Step 3: zone generation
    const zoneGenJob = await createJob(api, journeyId, "zone_generation", "step3");
    const zoneGenDone = await waitJobCompleted(api, zoneGenJob.id, "step3");
    const zonesAfterGenRes = await api.get(`/journeys/${journeyId}/zones`);
    const zonesAfterGen = await getJsonOrThrow(zonesAfterGenRes, "step3/list_zones");
    if (!zonesAfterGen?.zones?.length) {
      throw new Error("step3 expected generated zones > 0");
    }
    evidence.steps.step3 = {
      job_id: zoneGenDone.id,
      zones_total: zonesAfterGen.total_count,
    };
    log("3", `PASS zones_total=${zonesAfterGen.total_count}`);

    // Step 4: zone enrichment + comparison payload available
    const enrichJob = await createJob(api, journeyId, "zone_enrichment", "step4");
    const enrichDone = await waitJobCompleted(api, enrichJob.id, "step4");
    const zonesAfterEnrichRes = await api.get(`/journeys/${journeyId}/zones`);
    const zonesAfterEnrich = await getJsonOrThrow(zonesAfterEnrichRes, "step4/list_zones");
    const firstZone = zonesAfterEnrich.zones[0];
    if (!firstZone || !firstZone.fingerprint) {
      throw new Error("step4 expected first zone fingerprint");
    }
    evidence.steps.step4 = {
      job_id: enrichDone.id,
      zones_completed: zonesAfterEnrich.completed_count,
      selected_zone_fingerprint: firstZone.fingerprint,
      badges_provisional: Boolean(firstZone.badges_provisional),
    };
    log("4", `PASS zones_completed=${zonesAfterEnrich.completed_count}`);

    // Step 5: listings search request
    const step5Res = await api.post(`/journeys/${journeyId}/listings/search`, {
      data: {
        zone_fingerprint: firstZone.fingerprint,
        search_location_normalized: "lapa",
        search_location_label: "Lapa",
        search_location_type: "neighborhood",
        search_type: "rent",
        usage_type: "residential",
      },
    });
    const step5Data = await getJsonOrThrow(step5Res, "step5/listings_search");
    evidence.steps.step5 = {
      source: step5Data.source,
      freshness_status: step5Data.freshness_status,
      total_count: step5Data.total_count,
    };
    log("5", `PASS source=${step5Data.source} total_count=${step5Data.total_count}`);

    // Step 6: final listings read + dashboard rollups read
    const step6ListingsRes = await api.get(
      `/journeys/${journeyId}/zones/${firstZone.fingerprint}/listings?search_type=rent&usage_type=residential`,
    );
    const step6Listings = await getJsonOrThrow(step6ListingsRes, "step6/get_zone_listings");

    const step6RollupsRes = await api.get(
      `/journeys/${journeyId}/zones/${firstZone.fingerprint}/price-rollups?search_type=rent&days=30`,
    );
    let rollupsAvailable = false;
    let step6Rollups = [];
    if (step6RollupsRes.status() === 404) {
      rollupsAvailable = false;
    } else {
      step6Rollups = await getJsonOrThrow(step6RollupsRes, "step6/get_price_rollups");
      rollupsAvailable = true;
    }

    evidence.steps.step6 = {
      listings_source: step6Listings.source,
      listings_total_count: step6Listings.total_count,
      rollups_available: rollupsAvailable,
      rollups_count: Array.isArray(step6Rollups) ? step6Rollups.length : 0,
    };
    log(
      "6",
      `PASS listings_total=${step6Listings.total_count} rollups_count=${evidence.steps.step6.rollups_count}`,
    );

    evidence.outcome = "pass";
    evidence.finished_at = new Date().toISOString();
    console.log(JSON.stringify(evidence, null, 2));
  } catch (error) {
    evidence.outcome = "fail";
    evidence.error = error?.message || String(error);
    evidence.finished_at = new Date().toISOString();
    console.log(JSON.stringify(evidence, null, 2));
    throw error;
  } finally {
    await api.dispose();
  }
}

main().catch((error) => {
  console.error(`[verify_e2e_steps_1_6_playwright] ${error.message}`);
  process.exit(1);
});
