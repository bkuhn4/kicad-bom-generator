def recalc_status(row: dict, threshold: int):
    """Compute status/status_reason in-place from row data."""
    if not (row.get("mpn") or "").strip():
        row["status"] = "red"
        row["status_reason"] = "Missing MPN"
        return
    has_dist = row.get("digikey_pn") or row.get("mouser_pn")
    if not has_dist:
        row["status"] = "yellow"
        row["status_reason"] = "No distributor PN found"
        return
    stock = row.get("stock", 0)
    if isinstance(stock, int) and stock > threshold:
        row["status"] = "green"
        row["status_reason"] = ""
    elif isinstance(stock, int) and stock == 0:
        row["status"] = "red"
        row["status_reason"] = "Out of stock"
    elif isinstance(stock, int):
        row["status"] = "yellow"
        row["status_reason"] = f"Low stock: {stock} units (threshold: {threshold})"
    else:
        row["status"] = "yellow"
        row["status_reason"] = "Stock not yet checked"
