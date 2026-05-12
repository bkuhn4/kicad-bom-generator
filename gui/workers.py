from PyQt6.QtCore import QThread, pyqtSignal
from typing import Callable


class FetchAllWorker(QThread):
    progress = pyqtSignal(int, dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, rows, digikey_client, mouser_client, config):
        super().__init__()
        self.rows = rows
        self.dk = digikey_client
        self.mu = mouser_client
        self.config = config
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            threshold = self.config.get("low_stock_threshold", 10)
            for i, row in enumerate(self.rows):
                if self._cancel:
                    break
                mpn = row.get("mpn", "").strip()
                if not mpn:
                    self.progress.emit(i, {"status": "red", "status_reason": "Missing MPN"})
                    continue

                result = {}
                packaging = row.get("packaging", "Cut Tape")

                if self.dk.is_configured():
                    dk_data = self.dk.search_by_mpn(mpn, packaging)
                    if dk_data:
                        for k, v in dk_data.items():
                            # Never overwrite the user's packaging selection from the API
                            if k == "packaging":
                                continue
                            # Don't clobber an existing good value with an empty one
                            if v != "" and v is not None:
                                result[k] = v

                if self.mu.is_configured():
                    mu_data = self.mu.search_by_mpn(mpn)
                    if mu_data:
                        result.setdefault("mouser_pn", mu_data.get("mouser_pn", ""))
                        if not result.get("stock"):
                            result["stock"] = mu_data.get("stock", 0)
                        if not result.get("description"):
                            result["description"] = mu_data.get("description", "")
                        if not result.get("manufacturer"):
                            result["manufacturer"] = mu_data.get("manufacturer", "")

                stock = result.get("stock", 0)
                has_dist = result.get("digikey_pn") or result.get("mouser_pn")
                if has_dist:
                    if isinstance(stock, int) and stock > threshold:
                        result["status"] = "green"
                        result["status_reason"] = ""
                    elif isinstance(stock, int) and stock == 0:
                        result["status"] = "red"
                        result["status_reason"] = "Out of stock"
                    elif isinstance(stock, int):
                        result["status"] = "yellow"
                        result["status_reason"] = f"Low stock: {stock} units (threshold: {threshold})"
                    else:
                        result["status"] = "yellow"
                        result["status_reason"] = "Stock unknown after fetch"
                elif result:
                    result["status"] = "yellow"
                    result["status_reason"] = "No distributor PN returned by API"
                else:
                    result["status"] = "red"
                    result["status_reason"] = "Fetch returned no data"

                self.progress.emit(i, result)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class TestApiWorker(QThread):
    """Runs a single test_connection() call off the main thread."""
    done = pyqtSignal(bool, str)  # success, message

    def __init__(self, test_fn: Callable):
        super().__init__()
        self._test_fn = test_fn

    def run(self):
        ok, msg = self._test_fn()
        self.done.emit(ok, msg)


class SearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, keyword, digikey_client, mouser_client):
        super().__init__()
        self.keyword = keyword
        self.dk = digikey_client
        self.mu = mouser_client

    def run(self):
        try:
            results = []
            if self.dk.is_configured():
                for r in self.dk.search_keyword(self.keyword, limit=10):
                    r["source"] = "DigiKey"
                    results.append(r)
            if self.mu.is_configured():
                for r in self.mu.search_keyword(self.keyword, limit=10):
                    r["source"] = "Mouser"
                    results.append(r)
            self.results_ready.emit(results)
        except Exception as e:
            self.error.emit(str(e))
