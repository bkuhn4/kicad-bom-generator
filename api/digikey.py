from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

REDIRECT_URI  = "https://localhost:8139/digikey_callback"
_AUTH_PROD    = "https://api.digikey.com/v1/oauth2/authorize"
_AUTH_SB      = "https://sandbox-api.digikey.com/v1/oauth2/authorize"
_TOKEN_PROD   = "https://api.digikey.com/v1/oauth2/token"
_TOKEN_SB     = "https://sandbox-api.digikey.com/v1/oauth2/token"
_SEARCH_PROD  = "https://api.digikey.com/products/v4/search/keyword"
_SEARCH_SB    = "https://sandbox-api.digikey.com/products/v4/search/keyword"

AUTH_REQUIRED = "AUTH_REQUIRED"


class DigiKeyClient:
    def __init__(self, config: dict):
        self.config = config

    @property
    def _sandbox(self) -> bool:
        return self.config.get("digikey", {}).get("sandbox", False)

    @property
    def _token_path(self) -> Path:
        return Path.home() / ".kicad_bom_enhancer" / "digikey_tokens" / "token_storage.json"

    def is_configured(self) -> bool:
        dk = self.config.get("digikey", {})
        return bool(dk.get("client_id") and dk.get("client_secret"))

    def has_token(self) -> bool:
        return self._token_path.exists()

    def build_auth_url(self) -> str:
        dk = self.config.get("digikey", {})
        base = _AUTH_SB if self._sandbox else _AUTH_PROD
        params = {
            "client_id":     dk.get("client_id", ""),
            "response_type": "code",
            "redirect_uri":  REDIRECT_URI,
        }
        return base + "?" + urlencode(params)

    def exchange_code_for_token(self, code: str) -> tuple[bool, str]:
        dk = self.config.get("digikey", {})
        token_url = _TOKEN_SB if self._sandbox else _TOKEN_PROD
        try:
            r = requests.post(token_url, data={
                "grant_type":    "authorization_code",
                "code":          code,
                "client_id":     dk.get("client_id", ""),
                "client_secret": dk.get("client_secret", ""),
                "redirect_uri":  REDIRECT_URI,
            }, timeout=15)
            r.raise_for_status()
            token = r.json()
            token["expires"] = int(token["expires_in"]) + datetime.now(timezone.utc).timestamp() - 60
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_path, "w") as f:
                json.dump(token, f)
            return True, "Token saved."
        except Exception as e:
            return False, str(e)

    # ── internal token management ─────────────────────────────────────────────

    def _load_token(self) -> dict | None:
        try:
            with open(self._token_path) as f:
                return json.load(f)
        except Exception:
            return None

    def _save_token(self, token: dict):
        with open(self._token_path, "w") as f:
            json.dump(token, f)

    def _refresh_access_token(self, refresh_token: str) -> dict | None:
        dk = self.config.get("digikey", {})
        token_url = _TOKEN_SB if self._sandbox else _TOKEN_PROD
        try:
            r = requests.post(token_url, data={
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
                "client_id":     dk.get("client_id", ""),
                "client_secret": dk.get("client_secret", ""),
            }, timeout=15)
            r.raise_for_status()
            token = r.json()
            token["expires"] = int(token["expires_in"]) + datetime.now(timezone.utc).timestamp() - 60
            return token
        except Exception:
            return None

    def _get_access_token(self) -> str | None:
        """Return a valid access token, refreshing if expired. None means re-auth needed."""
        token = self._load_token()
        if token is None:
            return None

        if datetime.now(timezone.utc).timestamp() < token.get("expires", 0):
            return token.get("access_token")

        new_token = self._refresh_access_token(token.get("refresh_token", ""))
        if new_token is None:
            return None
        self._save_token(new_token)
        return new_token.get("access_token")

    def _headers(self, access_token: str) -> dict:
        dk = self.config.get("digikey", {})
        return {
            "Authorization":             f"Bearer {access_token}",
            "X-DIGIKEY-Client-Id":       dk.get("client_id", ""),
            "Content-Type":              "application/json",
            "X-DIGIKEY-Locale-Site":     "US",
            "X-DIGIKEY-Locale-Language": "en",
            "X-DIGIKEY-Locale-Currency": "USD",
        }

    def _search_url(self) -> str:
        return _SEARCH_SB if self._sandbox else _SEARCH_PROD

    # ── public API ────────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Client ID or Secret is empty."
        if not self.has_token():
            return False, AUTH_REQUIRED

        access_token = self._get_access_token()
        if access_token is None:
            return False, AUTH_REQUIRED

        try:
            r = requests.post(
                self._search_url(),
                headers=self._headers(access_token),
                json={"Keywords": "GRM188R71C104KA01D", "RecordCount": 1},
                timeout=15,
            )
            if r.status_code == 401:
                return False, AUTH_REQUIRED
            r.raise_for_status()
            products = r.json().get("Products", [])
            if products:
                p     = products[0]
                mpn   = p.get("ManufacturerProductNumber", "?")
                stock = p.get("QuantityAvailable", "?")
                return True, f"Connected successfully.\nFound: {mpn}  |  Stock: {stock}"
            return True, "Connected successfully (no products returned for test query)."
        except Exception:
            return False, traceback.format_exc()

    def search_by_mpn(self, mpn: str, packaging: str = "Cut Tape") -> dict | None:
        if not self.is_configured():
            return None
        access_token = self._get_access_token()
        if access_token is None:
            return None
        try:
            r = requests.post(
                self._search_url(),
                headers=self._headers(access_token),
                json={"Keywords": mpn, "RecordCount": 10},
                timeout=15,
            )
            r.raise_for_status()
            products = r.json().get("Products", [])
            if not products:
                return None

            # Prefer actual components over eval boards / kits
            components = [p for p in products if _is_component(p)]
            pool = components if components else products

            best = None

            # First pass: exact MPN match
            for p in pool:
                if p.get("ManufacturerProductNumber", "").lower() == mpn.lower():
                    if _has_packaging(p, packaging):
                        best = p
                        break

            # Second pass: prefix match (handles suffix variants like -R, #PBF, etc.)
            if not best:
                for p in pool:
                    if p.get("ManufacturerProductNumber", "").lower().startswith(mpn.lower()):
                        if _has_packaging(p, packaging):
                            best = p
                            break

            return _parse(best or pool[0], preferred_packaging=packaging)
        except Exception as e:
            print(f"[DigiKey] search_by_mpn({mpn}): {e}")
            return None

    def search_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        if not self.is_configured():
            return []
        access_token = self._get_access_token()
        if access_token is None:
            return []
        try:
            r = requests.post(
                self._search_url(),
                headers=self._headers(access_token),
                json={"Keywords": keyword, "RecordCount": limit},
                timeout=15,
            )
            r.raise_for_status()
            return [_parse(p) for p in r.json().get("Products", [])]
        except Exception as e:
            print(f"[DigiKey] search_keyword({keyword}): {e}")
            return []


# ── response parsing ──────────────────────────────────────────────────────────

_EVAL_PREFIXES = ("EVAL", "KIT ", "DEV KIT", "DEMO BOARD", "REFERENCE DESIGN",
                  "BREAKOUT", "DEVELOPMENT KIT", "STARTER KIT")

def _is_component(p: dict) -> bool:
    """Return False for eval boards, kits, and demo hardware."""
    desc = p.get("Description", {})
    d = (
        (desc.get("ProductDescription", "") or desc.get("DetailedDescription", "")).upper()
        if isinstance(desc, dict) else str(desc).upper()
    )
    if any(d.startswith(prefix) for prefix in _EVAL_PREFIXES):
        return False
    cat = p.get("Category", {})
    cat_name = (cat.get("Name", "") or "").lower() if isinstance(cat, dict) else ""
    return not any(kw in cat_name for kw in ("eval", "kit", "demo", "development board"))


def _var_packaging(var: dict) -> str:
    # V4 API uses "PackageType" inside each ProductVariation
    pkg = var.get("PackageType") or var.get("Packaging", {})
    return pkg.get("Name", "") if isinstance(pkg, dict) else str(pkg) if pkg else ""


def _packaging(p: dict) -> str:
    for var in p.get("ProductVariations", []):
        val = _var_packaging(var)
        if val:
            return val
    pkg = p.get("PackageType") or p.get("Packaging", {})
    if isinstance(pkg, dict):
        return pkg.get("Name", "") or pkg.get("Value", "")
    return str(pkg) if pkg else ""


def _pkg_matches(pkg_name: str, preferred: str) -> bool:
    """Three-way match: Cut Tape / Tape & Reel / Digi-Reel."""
    p = pkg_name.lower()
    pref = preferred.lower()
    if "digi" in pref or "mouser" in pref:          # Digi-Reel / MouseReel
        return "digi" in p and "reel" in p
    elif "reel" in pref:                             # Tape & Reel
        return "reel" in p and "digi" not in p
    else:                                            # Cut Tape
        return "reel" not in p


def _has_packaging(p: dict, preferred: str) -> bool:
    """True if ANY variation of p matches the preferred packaging."""
    for var in p.get("ProductVariations", []):
        val = _var_packaging(var)
        if val and _pkg_matches(val, preferred):
            return True
    return _pkg_matches(_packaging(p), preferred)


def _parse(p: dict, preferred_packaging: str = "") -> dict:
    desc = p.get("Description", {})
    description = (
        desc.get("ProductDescription", "") or desc.get("DetailedDescription", "")
        if isinstance(desc, dict) else str(desc)
    )
    mfr = p.get("Manufacturer", {})
    manufacturer = mfr.get("Name", "") if isinstance(mfr, dict) else str(mfr)

    # Pick the variation that best matches preferred_packaging
    variations = p.get("ProductVariations", [])
    chosen_var = None
    if preferred_packaging and variations:
        for var in variations:
            val = _var_packaging(var)
            if val and _pkg_matches(val, preferred_packaging):
                chosen_var = var
                break
    if chosen_var is None and variations:
        chosen_var = variations[0]

    dk_pn = p.get("DigiKeyProductNumber", "")
    pkg_str = ""
    stock = p.get("QuantityAvailable", 0)
    if chosen_var:
        dk_pn = chosen_var.get("DigiKeyProductNumber", "") or dk_pn
        pkg_str = _var_packaging(chosen_var)
        stock = chosen_var.get("QuantityAvailableforPackageType", stock)
    if not dk_pn:
        for var in variations:
            dk_pn = var.get("DigiKeyProductNumber", "")
            if dk_pn:
                break

    return {
        "mpn":          p.get("ManufacturerProductNumber", ""),
        "manufacturer": manufacturer,
        "description":  description,
        "digikey_pn":   dk_pn,
        "stock":        stock,
        "packaging":    pkg_str or _packaging(p),
    }
