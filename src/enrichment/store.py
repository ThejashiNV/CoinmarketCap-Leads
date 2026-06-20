import json
import os
import threading

from utils.url_tools import normalize_url


MANDATORY_FIELDS = [
    "Official Website URL",
    "Official Email IDs",
    "LinkedIn URLs",
    "Telegram URLs",
]

NA = "N/A"
MAX_ATTEMPTS = 2


def _present(value):
    return bool(value) and str(value).strip().upper() != NA


def missing_fields(row):
    return [f for f in MANDATORY_FIELDS if not _present(row.get(f))]


def is_complete(row):
    return len(missing_fields(row)) == 0


class ResultsStore:
    """URL-keyed persistent store of enriched rows.

    Thread-safe: a per-instance Lock guards all reads and writes so multiple
    concurrent worker threads can call record() / should_process() safely.
    """

    def __init__(self, path):
        self.path = path
        self._data = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._data = data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    @staticmethod
    def _key(project_url):
        return normalize_url(project_url) or str(project_url).strip()

    def should_process(self, project_url):
        with self._lock:
            entry = self._data.get(self._key(project_url))
            if not isinstance(entry, dict):
                return True
            status = entry.get("status")
            if status in ("complete", "exhausted"):
                return False
            return entry.get("attempts", 0) < MAX_ATTEMPTS

    def record(self, project_url, row):
        """Persist a freshly enriched row and compute its status."""
        key = self._key(project_url)
        with self._lock:
            prev = self._data.get(key, {})
            if not isinstance(prev, dict):
                prev = {}
            attempts = prev.get("attempts", 0) + 1

            if is_complete(row):
                status = "complete"
            elif attempts >= MAX_ATTEMPTS:
                status = "exhausted"
            else:
                status = "partial"

            self._data[key] = {"row": row, "status": status, "attempts": attempts}
            self._save()

    def get_row(self, project_url):
        with self._lock:
            entry = self._data.get(self._key(project_url))
            return entry.get("row") if isinstance(entry, dict) else None

    def rows_for(self, project_urls):
        """Return stored rows for the given URLs, in order (skips unknown)."""
        with self._lock:
            rows = []
            for url in project_urls:
                entry = self._data.get(self._key(url))
                if isinstance(entry, dict) and "row" in entry:
                    rows.append(entry["row"])
            return rows
