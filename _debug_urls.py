#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path("cods_ok").resolve()))
sys.path.insert(0, str(Path("apps/api/src").resolve()))

from realestate_meta_search import _vr_build_street_url_from_address, _zap_build_street_url_from_address
from modules.listings.scrapers.vivareal import _build_vivareal_scrape_url, _vr_parse_br_address

addr = "Rua Guaipa, Vila Leopoldina, Sao Paulo - SP"
print("legacy vr:", _vr_build_street_url_from_address(addr, mode="rent"))
print("legacy zap:", _zap_build_street_url_from_address(addr, mode="rent"))
parsed = _vr_parse_br_address(addr)
print("parsed addr:", parsed)
print("new vr start:", _build_vivareal_scrape_url(addr, "rent", []))
