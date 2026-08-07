"""
Background scheduler: periodic film-funding scans + a once-daily per-user digest.
Serves the PWA in a background thread so it stays responsive during a scan.
"""

import threading
import time
from datetime import datetime

from . import config, db, digest, scan, web


def run():
    threading.Thread(target=web.serve, daemon=True).start()
    print(f"[daemon] scanning every {config.SCAN_INTERVAL_MIN} min; "
          f"daily digest at {config.DIGEST_HOUR:02d}:00 local")
    last_digest_day = None
    # first scan on boot
    try:
        conn = db.init_db(config.DB_PATH)
        scan.scan(conn)
        conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[daemon] initial scan failed: {e}")
    next_scan = time.time() + config.SCAN_INTERVAL_MIN * 60
    while True:
        now = datetime.now()
        if now.hour == config.DIGEST_HOUR and last_digest_day != now.date():
            try:
                conn = db.init_db(config.DB_PATH)
                digest.run_digests(conn)
                conn.close()
            except Exception as e:  # noqa: BLE001
                print(f"[daemon] digest failed: {e}")
            last_digest_day = now.date()
        if time.time() >= next_scan:
            try:
                conn = db.init_db(config.DB_PATH)
                scan.scan(conn)
                conn.close()
            except Exception as e:  # noqa: BLE001
                print(f"[daemon] scan failed: {e}")
            next_scan = time.time() + config.SCAN_INTERVAL_MIN * 60
        time.sleep(60)
