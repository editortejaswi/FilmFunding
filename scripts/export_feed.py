#!/usr/bin/env python3
"""Export the opportunities table to a static web/opportunities.json.
Standalone (stdlib only) so it runs in CI without importing the app package.

Usage: python scripts/export_feed.py [DB_PATH] [OUT_PATH]
Defaults: filmfund.db  ->  web/opportunities.json
"""
import json, sqlite3, sys
from datetime import date, datetime, timezone

DB = sys.argv[1] if len(sys.argv) > 1 else "filmfund.db"
OUT = sys.argv[2] if len(sys.argv) > 2 else "web/opportunities.json"


def clean(r: sqlite3.Row) -> dict:
    d = dict(r)
    return {
        "id": d["fingerprint"],
        "title": d["title"],
        "url": d["url"],
        "org": d.get("org") or "",
        "source": d.get("source") or "",
        "region": d.get("country") or "",
        "deadline": (d.get("deadline") or "")[:10],  # "" when undated
        "kind": d.get("kind") or "",
        "value_inr": d.get("est_value_inr") or 0,
        "note": (d.get("fit_note") or d.get("summary") or "")[:240],
        "score": d.get("score") or 0,
    }


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM opportunities").fetchall()
    opps = [clean(r) for r in rows]
    today = date.today().isoformat()
    opps.sort(key=lambda o: (0 if (o["deadline"] and o["deadline"] >= today) else 1,
                             o["deadline"] or "9999", -o["score"]))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "count": len(opps),
        "opportunities": opps,
    }
    import os
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"wrote {OUT}: {len(opps)} opportunities")


if __name__ == "__main__":
    main()
