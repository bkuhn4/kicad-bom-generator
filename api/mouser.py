from __future__ import annotations

import traceback
import requests

_BASE = "https://api.mouser.com/api/v1"


class MouserClient:
    def __init__(self, config: dict):
        self.api_key = config.get("mouser", {}).get("api_key", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API Key is empty."
        try:
            resp = requests.post(
                f"{_BASE}/search/partnumber",
                params={"apiKey": self.api_key},
                json={"SearchByPartRequest": {"mouserPartNumber": "GRM188R71C104KA01D", "partSearchOptions": ""}},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            errors = data.get("Errors", [])
            if errors:
                return False, f"API returned error:\n{errors}"
            parts = data.get("SearchResults", {}).get("Parts", [])
            if parts:
                p = parts[0]
                return True, f"Connected successfully.\nFound: {p.get('ManufacturerPartNumber', '?')}  |  Stock: {p.get('Availability', '?')}"
            return True, "Connected successfully (no results for test query)."
        except Exception:
            return False, traceback.format_exc()

    def search_by_mpn(self, mpn: str) -> dict | None:
        if not self.is_configured():
            return None
        try:
            resp = requests.post(
                f"{_BASE}/search/partnumber",
                params={"apiKey": self.api_key},
                json={"SearchByPartRequest": {"mouserPartNumber": mpn, "partSearchOptions": ""}},
                timeout=10,
            )
            resp.raise_for_status()
            parts = resp.json().get("SearchResults", {}).get("Parts", [])
            return _parse(parts[0]) if parts else None
        except Exception as e:
            print(f"[Mouser] search_by_mpn({mpn}): {e}")
            return None

    def search_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        if not self.is_configured():
            return []
        try:
            resp = requests.post(
                f"{_BASE}/search/keyword",
                params={"apiKey": self.api_key},
                json={"SearchByKeywordRequest": {
                    "keyword": keyword, "records": limit,
                    "startingRecord": 0, "searchOptions": "", "searchWithSourcing": "",
                }},
                timeout=10,
            )
            resp.raise_for_status()
            parts = resp.json().get("SearchResults", {}).get("Parts", [])
            return [_parse(p) for p in parts]
        except Exception as e:
            print(f"[Mouser] search_keyword({keyword}): {e}")
            return []


def _parse(p: dict) -> dict:
    avail = p.get("Availability", "0")
    try:
        stock = int(avail.split()[0].replace(",", ""))
    except (ValueError, IndexError):
        stock = 0
    return {
        "mpn":        p.get("ManufacturerPartNumber", ""),
        "manufacturer": p.get("Manufacturer", ""),
        "description":  p.get("Description", ""),
        "mouser_pn":    p.get("MouserPartNumber", ""),
        "stock":        stock,
    }
