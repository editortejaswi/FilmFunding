# FilmFund Radar

A free, install-anywhere film-funding radar. Runs on everyone's phone, hosted on
free infrastructure — no personal server, no Pi.

## Architecture (all free tier)

```
GitHub Actions (daily cron)
  ├─ python -m filmfund.main scan      # find new grants/funds/open calls
  ├─ scripts/export_feed.py            # write web/opportunities.json (public feed)
  ├─ ping Supabase                     # keep the auth project from pausing (7d)
  └─ commit + deploy                   # heartbeat keeps cron alive (60d) + publishes

GitHub Pages  ->  serves web/ (the PWA)  ->  each phone installs + renders
Supabase Auth ->  email + password login, with password reset
```

- **Feed** is a static `web/opportunities.json` — public by design, scales for free.
- **Accounts** (email + password, reset) are handled by **Supabase Auth**; login
  gates only per-user data (saved calls, prefs), configured in `supabase/schema.sql`.
- Phones install the PWA via **Add to Home Screen** (iPhone + Android).

## One-time setup

1. **Supabase**: run `supabase/schema.sql` in the SQL Editor; set Authentication →
   Emails → SMTP (for reset/confirm mail); add this repo's Pages URL to
   Authentication → URL Configuration (Site URL + Redirect URLs).
2. **GitHub → Settings → Secrets and variables → Actions**, add:
   - `SUPABASE_URL` = `https://ffweqsdxdylmjdgzcifk.supabase.co`
   - `SUPABASE_ANON_KEY` = the publishable key
   - *(optional)* `GEMINI_API_KEY`, `FIRECRAWL_API_KEY` for richer scans
3. **GitHub → Settings → Pages** → Source = **GitHub Actions**.
4. Run the **scan-and-deploy** workflow once (Actions tab → Run workflow).

The app config (`web/index.html`) holds only the Supabase URL + publishable key,
both public-safe. Secrets never live in the repo (`.gitignore` enforces it).
