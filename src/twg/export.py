"""Dashboard data export utility according to SPEC.md §7."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from src.twg.store import TwgStore

SITE_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "site" / "data"
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)


class LiveDataExporter:
    """Exports site/data/live.json for static and dynamic dashboard consumption."""

    def __init__(self, store: TwgStore) -> None:
        self.store = store

    async def generate_live_json(self) -> Dict[str, Any]:
        now = int(time.time())
        raw_hourly = await self.store.http.get_kv("twg-stats", "hourly")
        hourly_data = {}
        if raw_hourly:
            try:
                hourly_data = json.loads(raw_hourly)
            except Exception:
                pass

        raw_open = await self.store.http.get_kv("twg-index", "open")
        open_job_ids = []
        if raw_open:
            try:
                open_job_ids = json.loads(raw_open).get("ids", [])
            except Exception:
                pass

        open_jobs = []
        for jid in open_job_ids[:10]:
            j = await self.store.get_job(jid)
            if j:
                open_jobs.append({
                    "id": j.get("id"),
                    "kind": j.get("kind"),
                    "sla": j.get("sla"),
                    "by": j.get("by"),
                    "in": j.get("in"),
                })

        payload = {
            "v": 1,
            "generated": now,
            "sources": {
                "hourly": "/kv/twg-stats/hourly",
                "open": "/kv/twg-index/open",
                "board": "/r/d-twg-board",
            },
            "hourly": hourly_data,
            "open_jobs": open_jobs,
            "agents": [],
        }

        # Write to site/data/live.json
        out_file = SITE_DATA_DIR / "live.json"
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

        return payload
