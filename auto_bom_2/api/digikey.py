import os
import traceback
from pathlib import Path

try:
    import digikey
    _DIGIKEY_LIB = True
except ImportError:
    _DIGIKEY_LIB = False


class DigiKeyClient:
    def __init__(self, config: dict):
        self.config = config

    def _configure(self):
        """Apply credentials to env vars every time before an API call."""
        dk = self.config.get("digikey", {})
        os.environ["DIGIKEY_CLIENT_ID"] = dk.get("client_id", "")
        os.environ["DIGIKEY_CLIENT_SECRET"] = dk.get("client_secret", "")
        os.environ["DIGIKEY_CLIENT_SANDBOX"] = str(dk.get("sandbox", False)).lower()
        token_dir = Path.home() / ".kicad_bom_enhancer" / "digikey_tokens"
        token_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DIGIKEY_STORAGE_PATH"] = str(token_dir)

    def is_configured(self) -> bool:
        if not _DIGIKEY_LIB:
            return False
        dk = self.config.get("digikey", {})
        return bool(dk.get("client_id") and dk.get("client_secret"))

    def test_connection(self) -> tuple[bool, str]:
        """
        Returns (success, message).
        On first use this will open a browser for OAuth2 — that is expected.
        """
        if not _DIGIKEY_LIB:
            return False, "digikey-api library is not installed.\nRun: pip install digikey-api"
        dk = self.config.get("digikey", {})
        if not dk.get("client_id"):
            return False, "Client ID is empty."
        if not dk.get("client_secret"):
            return False, "Client Secret is empty."
        try:
            self._configure()
            # Use a well-known MPN as a canary search
            result = digikey.keyword_search(keyword="GRM188R71C104KA01D", record_count=1)
            if result and result.products:
                p = result.products[0]
                mpn = getattr(p, "manufacturer_part_number", "?")
                stock = getattr(p, "quantity_available", "?")
                return True, f"Connected successfully.\nFound: {mpn}  |  Stock: {stock}"
            return True, "Connected successfully (no products returned for test query)."
        except Exception:
            return False, traceback.format_exc()

    def search_by_mpn(self, mpn: str, packaging: str = "Cut Tape") -> dict | None:
        if not self.is_configured():
            return None
        try:
            self._configure()
            result = digikey.keyword_search(keyword=mpn, record_count=10)
            if not result or not result.products:
                return None

            target_reel = "reel" in packaging.lower()
            best = None
            for p in result.products:
                if p.manufacturer_part_number.lower() == mpn.lower():
                    pkg_val = (p.packaging.value or "").lower() if p.packaging else ""
                    if ("reel" in pkg_val) == target_reel:
                        best = p
                        break
            if best is None:
                best = result.products[0]

            return _parse(best)
        except Exception as e:
            print(f"[DigiKey] search_by_mpn({mpn}): {e}")
            return None

    def search_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        if not self.is_configured():
            return []
        try:
            self._configure()
            result = digikey.keyword_search(keyword=keyword, record_count=limit)
            if not result or not result.products:
                return []
            return [_parse(p) for p in result.products]
        except Exception as e:
            print(f"[DigiKey] search_keyword({keyword}): {e}")
            return []


def _parse(p) -> dict:
    def _safe(attr, default=""):
        try:
            v = getattr(p, attr, default)
            return v if v is not None else default
        except Exception:
            return default

    return {
        "mpn":          _safe("manufacturer_part_number"),
        "manufacturer": getattr(p.manufacturer, "value", "") if p.manufacturer else "",
        "description":  _safe("product_description"),
        "digikey_pn":   _safe("digi_key_part_number"),
        "stock":        _safe("quantity_available", 0),
        "packaging":    getattr(p.packaging, "value", "") if p.packaging else "",
    }
