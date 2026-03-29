from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
	sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

import src.modules.zones.service as zone_service_module  # noqa: E402
from src.modules.zones.candidate_generation import CandidateZone, CandidateZoneGenerationError  # noqa: E402
from src.modules.zones.service import ZoneService  # noqa: E402


class _FakeMappings:
	def __init__(self, *, first_row=None, one_row=None):
		self._first_row = first_row
		self._one_row = one_row

	def first(self):
		return self._first_row

	def one(self):
		if self._one_row is None:
			raise RuntimeError("Expected one row")
		return self._one_row


class _FakeResult:
	def __init__(self, *, first_row=None, one_row=None):
		self._mappings = _FakeMappings(first_row=first_row, one_row=one_row)

	def mappings(self):
		return self._mappings


class _FakeConn:
	def __init__(self, *, context_row, existing_zone_rows, created_zone_ids):
		self.context_row = context_row
		self.existing_zone_rows = list(existing_zone_rows)
		self.created_zone_ids = list(created_zone_ids)
		self.deleted_previous_associations = False
		self.cleared_selected_zone = False
		self.insert_zone_params = []
		self.association_params = []

	async def execute(self, statement, params):
		sql = str(statement)
		if "FROM jobs jb" in sql:
			return _FakeResult(first_row=self.context_row)
		if "DELETE FROM journey_zones" in sql:
			self.deleted_previous_associations = True
			return _FakeResult()
		if "UPDATE journeys" in sql and "selected_zone_id = NULL" in sql:
			self.cleared_selected_zone = True
			return _FakeResult()
		if "FROM zones" in sql and "fingerprint = :fingerprint" in sql:
			return _FakeResult(first_row=self.existing_zone_rows.pop(0))
		if "INSERT INTO zones" in sql:
			self.insert_zone_params.append(params)
			return _FakeResult(one_row={"id": self.created_zone_ids.pop(0)})
		if "INSERT INTO journey_zones" in sql:
			self.association_params.append(params)
			return _FakeResult()
		raise AssertionError(f"Unexpected SQL executed: {sql}")


class _FakeBeginCtx:
	def __init__(self, conn):
		self._conn = conn

	async def __aenter__(self):
		return self._conn

	async def __aexit__(self, exc_type, exc, tb):
		return False


class _FakeEngine:
	def __init__(self, conn):
		self._conn = conn

	def connect(self):
		return _FakeBeginCtx(self._conn)

	def begin(self):
		return _FakeBeginCtx(self._conn)


def test_zone_service_generates_zones_from_legacy_candidates(monkeypatch) -> None:
	service = ZoneService(valhalla_adapter=object(), otp_adapter=object())
	journey_id = uuid4()
	selected_transport_point_id = uuid4()
	created_zone_id = uuid4()
	reused_zone_id = uuid4()

	context_row = {
		"journey_id": journey_id,
		"input_snapshot": {
			"transport_mode": "transit",
			"public_transport_mode": "rail",
			"max_travel_time_min": 35,
			"zone_radius_meters": 900,
			"dataset_version_id": "11111111-1111-1111-1111-111111111111",
		},
		"transport_point_id": selected_transport_point_id,
		"transport_point_source": "geosampa_metro_station",
		"transport_point_modal_types": ["metro"],
		"lat": -23.55052,
		"lon": -46.63331,
	}
	fake_conn = _FakeConn(
		context_row=context_row,
		existing_zone_rows=[None, {"id": reused_zone_id}],
		created_zone_ids=[created_zone_id],
	)
	helper_calls = []

	async def _fake_generate_candidate_zones_for_seed(**kwargs):
		helper_calls.append(kwargs)
		return [
			CandidateZone(
				logical_id="candidate-bus-1",
				mode="bus",
				source_point_id="stop-1",
				travel_time_minutes=13.6,
				centroid_lon=-46.63,
				centroid_lat=-23.55,
				geometry={
					"type": "Polygon",
					"coordinates": [[[-46.63, -23.55], [-46.631, -23.55], [-46.631, -23.551], [-46.63, -23.55]]],
				},
			),
			CandidateZone(
				logical_id="candidate-rail-1",
				mode="rail",
				source_point_id="station-1",
				travel_time_minutes=22.2,
				centroid_lon=-46.64,
				centroid_lat=-23.56,
				geometry={
					"type": "Polygon",
					"coordinates": [[[-46.64, -23.56], [-46.641, -23.56], [-46.641, -23.561], [-46.64, -23.56]]],
				},
			),
		]

	monkeypatch.setattr("src.modules.zones.service.get_engine", lambda: _FakeEngine(fake_conn))
	monkeypatch.setattr(
		"src.modules.zones.service.generate_candidate_zones_for_seed",
		_fake_generate_candidate_zones_for_seed,
	)

	outcome = asyncio.run(service.ensure_zones_for_job(uuid4()))

	assert len(helper_calls) == 1
	assert helper_calls[0]["seed_lat"] == -23.55052
	assert helper_calls[0]["seed_lon"] == -46.63331
	assert helper_calls[0]["radius_meters"] == 900
	assert helper_calls[0]["max_time_minutes"] == 35
	assert helper_calls[0]["public_transport_mode"] == "rail"
	assert fake_conn.deleted_previous_associations is True
	assert fake_conn.cleared_selected_zone is True
	assert len(fake_conn.insert_zone_params) == 1
	assert fake_conn.insert_zone_params[0]["transport_point_id"] == selected_transport_point_id
	assert fake_conn.insert_zone_params[0]["modal"] == "bus"
	assert fake_conn.insert_zone_params[0]["max_time_minutes"] == 14
	assert len(fake_conn.association_params) == 2
	assert fake_conn.association_params[0]["transport_point_id"] == selected_transport_point_id
	assert outcome["total"] == 2
	assert outcome["completed"] == 1
	assert [zone.reused for zone in outcome["zones"]] == [False, True]


def test_zone_service_rejects_incompatible_public_transport_seed(monkeypatch) -> None:
	service = ZoneService(valhalla_adapter=object(), otp_adapter=object())

	context_row = {
		"journey_id": uuid4(),
		"input_snapshot": {
			"transport_mode": "transit",
			"public_transport_mode": "bus",
			"max_travel_time_min": 35,
			"zone_radius_meters": 900,
		},
		"transport_point_id": uuid4(),
		"transport_point_source": "geosampa_metro_station",
		"transport_point_modal_types": ["metro"],
		"lat": -23.55052,
		"lon": -46.63331,
	}
	fake_conn = _FakeConn(
		context_row=context_row,
		existing_zone_rows=[],
		created_zone_ids=[],
	)

	async def _unexpected_generate_candidate_zones_for_seed(**kwargs):
		raise AssertionError("candidate generation should not run for incompatible seed")

	monkeypatch.setattr("src.modules.zones.service.get_engine", lambda: _FakeEngine(fake_conn))
	monkeypatch.setattr(
		"src.modules.zones.service.generate_candidate_zones_for_seed",
		_unexpected_generate_candidate_zones_for_seed,
	)

	try:
		asyncio.run(service.ensure_zones_for_job(uuid4()))
	except RuntimeError as exc:
		assert "bus-only" in str(exc)
	else:
		raise AssertionError("Expected incompatible public transport seed to fail")


def test_zone_service_propagates_bus_candidate_generation_failure(monkeypatch) -> None:
	service = ZoneService(valhalla_adapter=object(), otp_adapter=object())
	journey_id = uuid4()
	transport_point_id = uuid4()

	context_row = {
		"journey_id": journey_id,
		"input_snapshot": {
			"transport_mode": "transit",
			"public_transport_mode": "bus",
			"max_travel_time_min": 35,
			"zone_radius_meters": 900,
		},
		"transport_point_id": transport_point_id,
		"transport_point_source": "geosampa_bus_stop",
		"transport_point_modal_types": ["bus"],
		"lat": -23.55052,
		"lon": -46.63331,
	}
	fake_conn = _FakeConn(
		context_row=context_row,
		existing_zone_rows=[],
		created_zone_ids=[],
	)

	async def _failing_generate_candidate_zones_for_seed(**kwargs):
		raise zone_service_module.CandidateZoneGenerationError(
			"No bus candidate zones could be generated from GTFS/GeoSampa for the selected seed"
		)

	monkeypatch.setattr("src.modules.zones.service.get_engine", lambda: _FakeEngine(fake_conn))
	monkeypatch.setattr(
		"src.modules.zones.service.generate_candidate_zones_for_seed",
		_failing_generate_candidate_zones_for_seed,
	)

	try:
		asyncio.run(service.ensure_zones_for_job(uuid4()))
	except zone_service_module.CandidateZoneGenerationError as exc:
		assert "bus candidate zones" in str(exc)
	else:
		raise AssertionError("Expected bus candidate generation failure to propagate")

	assert fake_conn.deleted_previous_associations is False
	assert fake_conn.cleared_selected_zone is False
	assert fake_conn.insert_zone_params == []
	assert fake_conn.association_params == []


def test_zone_service_generates_single_walk_isochrone_without_transport_seed(monkeypatch) -> None:
	class _FakeValhallaAdapter:
		async def isochrone(self, origin, costing, contours_minutes):
			assert round(origin.lat, 5) == -23.55052
			assert round(origin.lon, 5) == -46.63331
			assert costing == "pedestrian"
			assert contours_minutes == [20]
			return {
				"type": "FeatureCollection",
				"features": [
					{
						"type": "Feature",
						"geometry": {
							"type": "Polygon",
							"coordinates": [[[-46.63331, -23.55052], [-46.632, -23.55052], [-46.632, -23.549], [-46.63331, -23.55052]]],
						},
					}
				],
			}

	service = ZoneService(valhalla_adapter=_FakeValhallaAdapter(), otp_adapter=object())
	journey_id = uuid4()
	created_zone_id = uuid4()

	context_row = {
		"journey_id": journey_id,
		"input_snapshot": {
			"transport_mode": "walk",
			"max_travel_minutes": 20,
			"reference_point": {"lat": -23.55052, "lon": -46.63331},
		},
		"transport_point_id": None,
		"transport_point_source": None,
		"transport_point_modal_types": [],
		"lat": None,
		"lon": None,
	}
	fake_conn = _FakeConn(
		context_row=context_row,
		existing_zone_rows=[None],
		created_zone_ids=[created_zone_id],
	)

	async def _unexpected_generate_candidate_zones_for_seed(**kwargs):
		raise AssertionError("candidate generation should not run for walk mode")

	monkeypatch.setattr("src.modules.zones.service.get_engine", lambda: _FakeEngine(fake_conn))
	monkeypatch.setattr(
		"src.modules.zones.service.generate_candidate_zones_for_seed",
		_unexpected_generate_candidate_zones_for_seed,
	)

	outcome = asyncio.run(service.ensure_zones_for_job(uuid4()))

	assert fake_conn.deleted_previous_associations is True
	assert fake_conn.cleared_selected_zone is True
	assert len(fake_conn.insert_zone_params) == 1
	assert fake_conn.insert_zone_params[0]["transport_point_id"] is None
	assert fake_conn.insert_zone_params[0]["modal"] == "walking"
	assert fake_conn.insert_zone_params[0]["max_time_minutes"] == 20
	assert fake_conn.insert_zone_params[0]["radius_meters"] == 1600
	assert len(fake_conn.association_params) == 1
	assert fake_conn.association_params[0]["transport_point_id"] is None
	assert outcome["total"] == 1
	assert outcome["completed"] == 1
	assert [zone.reused for zone in outcome["zones"]] == [False]


def test_zone_service_generates_single_car_isochrone_without_transport_seed(monkeypatch) -> None:
	class _FakeValhallaAdapter:
		async def isochrone(self, origin, costing, contours_minutes):
			assert round(origin.lat, 5) == -23.55052
			assert round(origin.lon, 5) == -46.63331
			assert costing == "auto"
			assert contours_minutes == [30]
			return {
				"type": "FeatureCollection",
				"features": [
					{
						"type": "Feature",
						"geometry": {
							"type": "Polygon",
							"coordinates": [[[-46.63331, -23.55052], [-46.631, -23.55052], [-46.631, -23.548], [-46.63331, -23.55052]]],
						},
					}
				],
			}

	service = ZoneService(valhalla_adapter=_FakeValhallaAdapter(), otp_adapter=object())
	journey_id = uuid4()
	created_zone_id = uuid4()

	context_row = {
		"journey_id": journey_id,
		"input_snapshot": {
			"transport_mode": "car",
			"max_travel_minutes": 30,
			"reference_point": {"lat": -23.55052, "lon": -46.63331},
		},
		"transport_point_id": None,
		"transport_point_source": None,
		"transport_point_modal_types": [],
		"lat": None,
		"lon": None,
	}
	fake_conn = _FakeConn(
		context_row=context_row,
		existing_zone_rows=[None],
		created_zone_ids=[created_zone_id],
	)

	async def _unexpected_generate_candidate_zones_for_seed(**kwargs):
		raise AssertionError("candidate generation should not run for car mode")

	monkeypatch.setattr("src.modules.zones.service.get_engine", lambda: _FakeEngine(fake_conn))
	monkeypatch.setattr(
		"src.modules.zones.service.generate_candidate_zones_for_seed",
		_unexpected_generate_candidate_zones_for_seed,
	)

	outcome = asyncio.run(service.ensure_zones_for_job(uuid4()))

	assert fake_conn.deleted_previous_associations is True
	assert fake_conn.cleared_selected_zone is True
	assert len(fake_conn.insert_zone_params) == 1
	assert fake_conn.insert_zone_params[0]["transport_point_id"] is None
	assert fake_conn.insert_zone_params[0]["modal"] == "car"
	assert fake_conn.insert_zone_params[0]["max_time_minutes"] == 30
	assert fake_conn.insert_zone_params[0]["radius_meters"] == 15000
	assert len(fake_conn.association_params) == 1
	assert fake_conn.association_params[0]["transport_point_id"] is None
	assert outcome["total"] == 1
	assert outcome["completed"] == 1
	assert [zone.reused for zone in outcome["zones"]] == [False]
