#!/usr/bin/env python3
"""
FilmFund Radar — CLI.

  python3 -m filmfund.main serve            serve the PWA (default :8090)
  python3 -m filmfund.main scan             fetch new film-funding opportunities
  python3 -m filmfund.main seed             import pifiradar's film-funding rows (one-time)
  python3 -m filmfund.main digest           email each user their personal digest now
  python3 -m filmfund.main adduser <email>  register a filmmaker
  python3 -m filmfund.main invite <email>   email someone a sign-in link
  python3 -m filmfund.main icons            regenerate PWA icons
  python3 -m filmfund.main daemon           scan on a schedule + daily digests
  python3 -m filmfund.main stats            counts
"""

import sys

from . import auth, config, db, digest, icons, scan, web


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"
    conn = db.init_db(config.DB_PATH)

    if cmd == "serve":
        conn.close()
        web.serve()
    elif cmd == "scan":
        scan.scan(conn)
    elif cmd == "seed":
        scan.seed_from_pifiradar(conn)
    elif cmd == "digest":
        digest.run_digests(conn)
    elif cmd == "adduser" and len(args) > 1:
        uid = db.upsert_user(conn, args[1])
        print(f"registered {args[1]} (id {uid})")
    elif cmd == "invite" and len(args) > 1:
        auth.request_login(conn, args[1])
    elif cmd == "icons":
        icons.generate()
    elif cmd == "daemon":
        conn.close()
        from . import daemon
        daemon.run()
    elif cmd == "stats":
        c = db.bucket_counts(conn)
        u = len(db.all_users(conn))
        print(f"opportunities: {c['all']}  | live {c['']}  open {c['open']}  "
              f"<=7d {c['d7']}  closed {c['closed']}  undated {c['undated']}")
        print(f"users: {u}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
