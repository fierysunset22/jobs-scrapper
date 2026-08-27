"""Generate a self-contained dashboard.html from saved state + discovery feed.

The visual design mirrors the "Job Tracker Dark" Claude Design mockup (DM Sans /
DM Mono, oklch dark palette, live pill, stat cards, job table with NEW badges).
All data is real: jobs come from the saved state snapshots, "new" status from the
discovery-events feed, and logos from logo.dev (config token), with a colored
initial tile as fallback.

Everything (data + logo.dev token + domains, read from config.json) is embedded
into the HTML as JSON, so the file works by double-clicking it (file://). Web
fonts load from Google when online and fall back to system fonts offline.

Regenerated at the end of every run; also runnable standalone:

    python3 -m scraper.dashboard
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from scraper import prefs as prefs_store
from scraper import store


def _slug(company: str) -> str:
    return company.lower().replace("/", "-").replace(" ", "-")


def _relative(ts: str, today: date) -> str:
    """Best-effort 'how long ago' from a provider timestamp (ISO string or epoch
    seconds/millis). Returns '' when it can't be parsed."""
    if not ts:
        return ""
    s = str(ts).strip()
    try:
        if s.isdigit():
            v = int(s)
            if v > 1_000_000_000_000:  # epoch millis
                v //= 1000
            d = datetime.fromtimestamp(v, timezone.utc).date()
        else:
            d = datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, OSError, OverflowError):
        return ""
    days = (today - d).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1d ago"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def _is_remote(location: str) -> bool:
    return "remote" in (location or "").lower()


def collect(data_dir: Path, config: dict) -> dict:
    """Pull together everything the dashboard needs from disk + config."""
    today = date.today()
    today_str = today.isoformat()

    meta = {}
    for c in config.get("companies", []):
        meta[_slug(c["company"])] = {"name": c["company"],
                                     "domain": c.get("domain", "")}

    # Jobs discovered on today's run → drives "New Today" + the NEW badge.
    events_raw = store.load_events(data_dir)
    new_ids_today = {e["id"] for e in events_raw if e.get("date") == today_str}

    state_dir = data_dir / store.STATE_DIRNAME
    companies = []
    jobs = []
    remote_count = 0
    if state_dir.exists():
        for path in sorted(state_dir.glob("*.json")):
            info = meta.get(path.stem, {"name": path.stem.replace("-", " ").title(),
                                        "domain": ""})
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            roles = list(snapshot.values())
            companies.append({"company": info["name"], "domain": info["domain"],
                              "count": len(roles)})
            for r in roles:
                loc = r.get("location", "")
                if _is_remote(loc):
                    remote_count += 1
                jobs.append({
                    "id": r.get("id", ""),
                    "company": info["name"],
                    "domain": info["domain"],
                    "title": r.get("title", ""),
                    "location": loc,
                    "url": r.get("url", ""),
                    "remote": _is_remote(loc),
                    "isNew": r.get("id", "") in new_ids_today,
                    "updated": _relative(r.get("updated_at", ""), today),
                })

    # New roles first, then alphabetical by company + title.
    jobs.sort(key=lambda j: (not j["isNew"], j["company"].lower(), j["title"].lower()))

    # Machine-readable UTC instant; the browser formats it in the viewer's own
    # timezone. (Pre-formatting here would bake in the build machine's zone —
    # UTC on the CI runner — which is wrong for everyone reading it elsewhere.)
    status = store.load_run_status(data_dir) or {}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "update_ok": status.get("ok", True),
        "update_errors": status.get("errors", []),
        "logo_token": os.environ.get("LOGO_DEV_TOKEN")
        or config.get("logo_dev", {}).get("publishable_token", ""),
        "companies": sorted(companies, key=lambda c: c["company"]),
        "jobs": jobs,
        "total_jobs": len(jobs),
        "new_count": len(new_ids_today),
        "remote_count": remote_count,
        # Active filters applied during fetch
        "filters": config.get("filters", {}),
        # Followed / dismissed roles, embedded so the page renders correctly on
        # first paint (over HTTP the dashboard then reconciles via /api/prefs).
        "prefs": prefs_store.load_prefs(data_dir),
    }


def _load_config(config_path: Path) -> dict:
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def build_dashboard(data_dir: Path, out_path: Path,
                    config_path: Path | None = None) -> Path:
  config = _load_config(config_path) if config_path else {}
  data = collect(data_dir, config)
  # Write only the machine-readable per-run payload. Static assets live in
  # the dashboard directory and are managed separately (not rewritten).
  out_dir = out_path.parent
  out_dir.mkdir(parents=True, exist_ok=True)
  data_path = out_dir / "data.json"
  data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
  # Ensure a minimal index.html exists on first run for backwards
  # compatibility; otherwise leave static files untouched.
  idx = out_dir / "index.html"
  if not idx.exists():
    idx.write_text(
      """<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Job Tracker</title>\n<link rel=\"stylesheet\" href=\"/dashboard/styles.css\">\n</head>\n<body>\n<div id=\"app\">Loading…</div>\n<script>/* data loaded from data.json */</script>\n<script src=\"/dashboard/app.js\" defer></script>\n</body>\n</html>""",
      encoding="utf-8")
  return data_path


# The large single-file HTML template and embedded JS/CSS have been removed.
# Static files now live under the `dashboard/` directory and a per-run
# `data.json` is written by `build_dashboard()`.


if __name__ == "__main__":
        root = Path(__file__).resolve().parent.parent
        from scraper.env import load_env
        load_env(root / ".env")
        out = build_dashboard(root / "data", root / "dashboard" / "index.html",
                                                    root / "config.json")
        print(f"dashboard written to {out}")
