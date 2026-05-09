"""
DigiKey v3 Search API and Mouser v1 Search API wrappers.
All functions return empty lists / tuples on any error so callers never crash.
"""
from __future__ import annotations

import threading
import time
from typing import List, Tuple

import requests

from .models import PackagingVariant

import os
from pathlib import Path
import digikey
from digikey.v3.productinformation import KeywordSearchRequest
from mouser.api import MouserPartSearchRequest

# ------------------------------------------------------------------ #
# DigiKey and Mouser API Client Wrappers
# ------------------------------------------------------------------ #

def lookup_digikey(
    mpn: str,
    client_id: str,
    client_secret: str,
    preferred_pkg: str = "Tape & Reel (TR)",
) -> List[PackagingVariant]:
    if not (mpn and client_id and client_secret):
        return []

    # Configure Digikey-API library environment
    os.environ['DIGIKEY_CLIENT_ID'] = client_id
    os.environ['DIGIKEY_CLIENT_SECRET'] = client_secret
    os.environ['DIGIKEY_CLIENT_SANDBOX'] = 'False'
    
    dk_cache_dir = Path.home() / ".auto_bom" / "digikey_cache"
    dk_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ['DIGIKEY_STORAGE_PATH'] = str(dk_cache_dir)

    try:
        req = KeywordSearchRequest(keywords=mpn, record_count=25)
        result = digikey.keyword_search(body=req)
        
        products = []
        if getattr(result, 'exact_manufacturer_products', None):
            products.extend(result.exact_manufacturer_products)
        if not products and getattr(result, 'products', None):
            products.extend(result.products)
    except Exception:
        return []

    variants: List[PackagingVariant] = []
    seen: set = set()
    for p in products:
        mfg_pn = p.manufacturer_part_number.strip().upper() if getattr(p, 'manufacturer_part_number', None) else ""
        if mfg_pn != mpn.strip().upper():
            continue
            
        pkg = getattr(p, 'packaging', None)
        pkg_val = pkg.value if pkg else "Unknown"
        
        if pkg_val in seen:
            continue
        seen.add(pkg_val)
        
        try:
            price = float(p.unit_price) if getattr(p, 'unit_price', None) else 0.0
        except (TypeError, ValueError):
            price = 0.0
            
        variants.append(PackagingVariant(
            packaging_type=pkg_val,
            part_number=p.digi_key_part_number if getattr(p, 'digi_key_part_number', None) else "",
            stock=int(p.quantity_available) if getattr(p, "quantity_available", None) else 0,
            unit_price=price,
        ))

    # Sort by preferred packaging first
    _prefer_sort(variants, preferred_pkg)
    return variants


# ------------------------------------------------------------------ #
# Mouser
# ------------------------------------------------------------------ #

def lookup_mouser(
    mpn: str,
    api_key: str,
    preferred_pkg: str = "Tape & Reel (TR)",
) -> List[PackagingVariant]:
    if not (mpn and api_key):
        return []

    # Configure Mouser API environment variable
    os.environ['MOUSER_PART_API_KEY'] = api_key

    try:
        req = MouserPartSearchRequest('keyword')
        if not req.part_search(mpn):
            return []
        
        # get raw response dictionary from mouser library
        data = req.get_response()
        parts = data.get("SearchResults", {}).get("Parts", [])
        if not parts:
            parts = []
    except Exception:
        return []

    variants: List[PackagingVariant] = []
    seen: set = set()
    for p in parts:
        if p.get("ManufacturerPartNumber", "").strip().upper() != mpn.strip().upper():
            continue
        pkg_label = _classify_mouser_pkg(p)
        if pkg_label in seen:
            continue
        seen.add(pkg_label)

        avail_str = p.get("Availability", "0").replace(",", "").split(" ")[0]
        try:
            stock = int(avail_str)
        except ValueError:
            stock = 0

        price_breaks = p.get("PriceBreaks", [])
        try:
            price = float(str(price_breaks[0].get("Price", "0")).replace("$", "").replace(",", ""))
        except (IndexError, ValueError, TypeError):
            price = 0.0

        variants.append(PackagingVariant(
            packaging_type=pkg_label,
            part_number=p.get("MouserPartNumber", ""),
            stock=stock,
            unit_price=price,
        ))

    _prefer_sort(variants, preferred_pkg)
    return variants


def _classify_mouser_pkg(part: dict) -> str:
    pn   = part.get("MouserPartNumber", "").upper()
    desc = (part.get("Description", "") + " " + part.get("ProductAttributes", "")).upper()
    if "TAPE & REEL" in desc or "-TR" in pn or "T&R" in desc or "TAPE AND REEL" in desc:
        return "Tape & Reel"
    if "DIGI-REEL" in desc or "MOUSER REEL" in desc:
        return "Mouser Reel"
    if "CUT TAPE" in desc or "-CT" in pn:
        return "Cut Tape"
    return "Cut Tape"


# ------------------------------------------------------------------ #
# LCSC (unofficial, best-effort)
# ------------------------------------------------------------------ #

_LCSC_SEARCH_URL = "https://wmsc.lcsc.com/wmsc/search/global"


def lookup_lcsc(mpn: str) -> Tuple[str, int]:
    """Return (lcsc_pn, stock). Returns ('', 0) on any failure."""
    if not mpn:
        return "", 0
    try:
        resp = requests.get(
            _LCSC_SEARCH_URL,
            params={"keyword": mpn, "currentPage": 1, "pageSize": 10},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=8,
        )
        resp.raise_for_status()
        products = (resp.json()
                    .get("result", {})
                    .get("productSearchResultVO", {})
                    .get("productList", []))
        for p in products:
            if p.get("productModel", "").strip().upper() == mpn.strip().upper():
                return p.get("productCode", ""), int(p.get("stockNumber", 0) or 0)
    except Exception:
        pass
    return "", 0


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_PKG_PREFERENCE = [
    "Tape & Reel (TR)", "Tape & Reel", "Cut Tape (CT)", "Cut Tape",
    "DigiReel®", "Mouser Reel",
]


def _prefer_sort(variants: List[PackagingVariant], preferred: str) -> None:
    """Sort variants so preferred packaging comes first."""
    order = [preferred] + [p for p in _PKG_PREFERENCE if p != preferred]
    def key(v: PackagingVariant) -> int:
        try:
            return order.index(v.packaging_type)
        except ValueError:
            return len(order)
    variants.sort(key=key)
