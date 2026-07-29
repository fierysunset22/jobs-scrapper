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
        # Followed / dismissed roles, embedded so the page renders correctly on
        # first paint (over HTTP the dashboard then reconciles via /api/prefs).
        "prefs": prefs_store.load_prefs(data_dir),
    }


def _escape_for_script(s: str) -> str:
    return s.replace("</", "<\\/")


def render(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return _TEMPLATE.replace("__PAYLOAD__", _escape_for_script(payload))


def _load_config(config_path: Path) -> dict:
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def build_dashboard(data_dir: Path, out_path: Path,
                    config_path: Path | None = None) -> Path:
    config = _load_config(config_path) if config_path else {}
    data = collect(data_dir, config)
    out_path.write_text(render(data), encoding="utf-8")
    return out_path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300..700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  @keyframes pdot { 0%,100%{transform:scale(1);opacity:1} 50%{transform:scale(1.65);opacity:.45} }
  @keyframes pring { 0%{box-shadow:0 0 0 0 rgba(74,222,128,.55)} 70%{box-shadow:0 0 0 8px rgba(74,222,128,0)} 100%{box-shadow:0 0 0 8px rgba(74,222,128,0)} }
  @keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }
  :root {
    --bg: oklch(0.14 0.02 260); --nav: oklch(0.13 0.02 260);
    --line: oklch(0.22 0.015 260); --line2: oklch(0.24 0.015 260);
    --muted: oklch(0.47 0.04 260); --muted2: oklch(0.52 0.04 260);
    --text: oklch(0.92 0.01 260); --text-hi: oklch(0.90 0.01 260);
    --panel: oklch(0.17 0.018 260); --card: oklch(0.185 0.02 260);
    --input: oklch(0.20 0.015 260); --inputbd: oklch(0.26 0.02 260);
    --blue: oklch(0.68 0.22 252); --blue2: oklch(0.66 0.22 252);
    --green: oklch(0.65 0.2 148);
  }
  * { box-sizing: border-box; }
  html { color-scheme: dark; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font-family: 'DM Sans', system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased; }
  .mono { font-family: 'DM Mono', ui-monospace, SFMono-Regular, monospace; }
  select { -webkit-appearance: none; appearance: none; cursor: pointer; }
  ::placeholder { color: oklch(0.42 0.03 260); }
  a { text-decoration: none; }
  .page { min-height: 100vh; display: flex; flex-direction: column; }

  /* Top nav */
  .nav { display: flex; align-items: center; gap: 16px; height: 56px;
    padding: 0 32px; background: var(--nav); border-bottom: 1px solid var(--line);
    position: sticky; top: 0; z-index: 5; }
  .brand { font-size: 15px; font-weight: 700; color: #fff; letter-spacing: -.02em; }
  .live { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px;
    border-radius: 999px; background: oklch(0.20 0.08 148); }
  .live .d { width: 6px; height: 6px; border-radius: 50%; background: var(--green);
    animation: pring 2s ease-out infinite; }
  .live span { font-size: 11px; font-weight: 600; color: var(--green); }
  .nav .upd { margin-left: auto; font-size: 12px; color: oklch(0.48 0.04 260); }
  .upd-status { display: inline-flex; align-items: center; justify-content: center;
    width: 16px; height: 16px; margin-left: 2px; border-radius: 50%;
    font-size: 11px; line-height: 1; cursor: default; }
  .upd-status.ok { color: var(--green); background: oklch(0.20 0.08 148); }
  .upd-status.warn { color: oklch(0.78 0.16 75); background: oklch(0.24 0.07 75); }
  .refresh { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px;
    border-radius: 7px; border: 1.5px solid oklch(0.28 0.02 260); background: transparent;
    color: oklch(0.75 0.04 260); font: 600 12px 'DM Sans', sans-serif; cursor: pointer; }
  .refresh:hover { border-color: oklch(0.34 0.02 260); }
  .refresh .ic { display: inline-block; font-size: 14px; line-height: 1; }
  .refresh.busy { color: var(--muted); cursor: not-allowed; }
  .refresh.busy .ic { animation: spin .7s linear infinite; }

  .head { padding: 28px 32px 0; }
  .head h1 { margin: 0 0 4px; font-size: 22px; font-weight: 700; color: #fff;
    letter-spacing: -.02em; }
  .head p { margin: 0; font-size: 13px; color: var(--muted2); }

  /* Alert banner */
  .banner { margin: 20px 32px 0; display: flex; align-items: center; gap: 10px;
    padding: 12px 18px; border-radius: 10px; }
  .banner.has { background: oklch(0.20 0.06 252); border: 1px solid oklch(0.26 0.09 252); }
  .banner.none { background: oklch(0.185 0.02 260); border: 1px solid var(--line); }
  .banner .d { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
  .banner.has .d { background: var(--blue); animation: pdot 2s ease-in-out infinite; }
  .banner.none .d { background: var(--green); }
  .banner .txt { font-size: 13px; font-weight: 600; }
  .banner.has .txt { color: oklch(0.84 0.1 252); }
  .banner.none .txt { color: oklch(0.7 0.04 260); }
  .banner .ct { margin-left: auto; font-size: 12px; color: oklch(0.55 0.08 252); }

  /* Stats */
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
    padding: 16px 32px; }
  .stat { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 16px 20px; }
  .stat .l { margin: 0 0 6px; font-size: 10px; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .1em; }
  .stat .n { margin: 0; font-size: 26px; font-weight: 700; line-height: 1;
    color: var(--text-hi); }
  .stat .n.blue { color: var(--blue); }

  /* Panel */
  .panel { margin: 0 32px 32px; background: var(--panel); border: 1px solid var(--line);
    border-radius: 12px; overflow: hidden; }
  .filterbar { display: flex; align-items: center; gap: 10px; padding: 12px 20px;
    border-bottom: 1px solid var(--line); }
  .search { position: relative; flex: 1; }
  .search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%);
    color: var(--muted); }
  .search input { width: 100%; padding: 8px 12px 8px 34px; border: 1.5px solid var(--inputbd);
    border-radius: 8px; font: 13px 'DM Sans', sans-serif; color: var(--text-hi);
    background: var(--input); outline: none; }
  .selwrap { position: relative; }
  .selwrap select { padding: 8px 28px 8px 12px; border: 1.5px solid var(--inputbd);
    border-radius: 8px; font: 13px 'DM Sans', sans-serif; color: var(--text-hi);
    background: var(--input); outline: none; }
  .selwrap .caret { position: absolute; right: 9px; top: 50%; transform: translateY(-50%);
    pointer-events: none; }
  .search input:focus, .selwrap select:focus { border-color: oklch(0.4 0.08 252); }

  .thead { display: flex; align-items: center; gap: 14px; padding: 8px 20px 8px 17px;
    background: oklch(0.165 0.018 260); border-bottom: 2px solid var(--line2); }
  .thead .h { font-size: 10px; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .1em; }
  .c-logo { width: 36px; flex-shrink: 0; }
  .c-role { flex: 1; min-width: 0; }
  .c-status { width: 68px; flex-shrink: 0; }
  .c-loc { width: 150px; flex-shrink: 0; }
  .c-upd { width: 64px; flex-shrink: 0; text-align: right; }
  .c-view { width: 70px; flex-shrink: 0; }

  .row { display: flex; align-items: center; gap: 14px; padding: 13px 20px 13px 17px;
    border-bottom: 1px solid oklch(0.215 0.015 260); border-left: 3px solid transparent;
    background: oklch(0.185 0.015 260); transition: background .12s; }
  .row:hover { background: oklch(0.205 0.018 260); }
  .row.new { background: oklch(0.215 0.048 252); border-left-color: var(--blue2); }
  .row.new:hover { background: oklch(0.23 0.052 252); }
  .logo { width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0;
    display: grid; place-items: center; overflow: hidden;
    box-shadow: inset 0 0 0 1px #ffffff1a; }
  .logo img { width: 100%; height: 100%; object-fit: contain; }
  .logo .ini { width: 100%; height: 100%; display: grid; place-items: center;
    color: #fff; font-weight: 700; font-size: 12px; }
  .title { font-size: 14px; font-weight: 600; color: oklch(0.92 0.01 260);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .co { font-size: 12px; color: var(--muted2); margin-top: 2px; }
  .badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px;
    background: var(--blue2); color: oklch(0.12 0.02 260); font-size: 10px; font-weight: 700;
    letter-spacing: .08em; }
  .chip { display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 500; white-space: nowrap; max-width: 100%;
    overflow: hidden; text-overflow: ellipsis; vertical-align: middle; box-sizing: border-box; }
  .chip.remote { background: oklch(0.25 0.1 160); color: oklch(0.72 0.16 160); }
  .chip.onsite { background: oklch(0.24 0.03 240); color: oklch(0.72 0.05 240); }
  .upd { font-size: 12px; color: var(--muted); }
  .view { display: inline-flex; align-items: center; justify-content: center; width: 70px;
    padding: 6px 0; border-radius: 7px; border: 1.5px solid var(--blue);
    color: oklch(0.72 0.15 252); font-size: 12px; font-weight: 600; }
  .view:hover { background: oklch(0.22 0.06 252); }
  .empty { padding: 48px; text-align: center; color: var(--muted); font-size: 14px; }

  /* Per-row action buttons (track / dismiss) */
  .c-act { width: 70px; flex-shrink: 0; }
  .acts { display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
  .iconbtn { width: 28px; height: 28px; display: grid; place-items: center; padding: 0;
    border-radius: 7px; border: 1.5px solid var(--inputbd); background: transparent;
    color: var(--muted2); font-size: 14px; line-height: 1; cursor: pointer;
    transition: color .12s, border-color .12s, background .12s; }
  .iconbtn:hover { border-color: oklch(0.34 0.02 260); color: var(--text-hi); }
  .iconbtn.track.on { color: oklch(0.82 0.16 85); border-color: oklch(0.5 0.12 85);
    background: oklch(0.24 0.07 85); }
  .iconbtn.drop:hover { color: oklch(0.72 0.18 25); border-color: oklch(0.45 0.14 25);
    background: oklch(0.22 0.06 25); }

  /* Tracked / following panel — pinned at the top, collapsed to a summary by default */
  .tracked { margin: 16px 32px 0; background: var(--panel);
    border: 1px solid oklch(0.34 0.07 85); border-radius: 12px; overflow: hidden; }
  .tracked-head { display: flex; align-items: center; gap: 10px; padding: 11px 20px;
    width: 100%; margin: 0; border: none; border-bottom: 1px solid var(--line); background: oklch(0.19 0.035 85);
    font: inherit; color: inherit; text-align: left; cursor: pointer; }
  .tracked-head:hover { background: oklch(0.21 0.04 85); }
  .tracked-title { font-size: 11px; font-weight: 700; color: oklch(0.84 0.15 85);
    letter-spacing: .1em; text-transform: uppercase; }
  .tracked-ct { font-size: 12px; color: var(--muted2); }
  .tracked-caret { margin-left: auto; flex-shrink: 0; color: oklch(0.7 0.1 85);
    transition: transform .15s; }
  .tracked-caret.open { transform: rotate(180deg); }

  /* "N no longer available" sub-group — collapsed within the panel until expanded */
  .gone-toggle { display: flex; align-items: center; gap: 8px; width: 100%; margin: 0;
    padding: 10px 20px; border: none; border-left: 3px solid oklch(0.6 0.18 25);
    background: oklch(0.17 0.03 25); color: oklch(0.72 0.1 25);
    font: 600 12.5px 'DM Sans', sans-serif; text-align: left; cursor: pointer; }
  .gone-toggle:hover { background: oklch(0.19 0.035 25); }
  .gone-toggle .car { margin-left: auto; flex-shrink: 0; transition: transform .15s; }
  .gone-toggle .car.open { transform: rotate(180deg); }

  /* No-longer-available highlight (tracked role that vanished from the feed) */
  .row.gone { background: oklch(0.2 0.045 25); border-left-color: oklch(0.6 0.18 25); }
  .row.gone:hover { background: oklch(0.22 0.05 25); }
  .row.gone .title { color: oklch(0.8 0.07 25); text-decoration: line-through;
    text-decoration-color: oklch(0.5 0.12 25); }
  .badge.gone { background: oklch(0.58 0.19 25); color: #fff; letter-spacing: .04em; }
  .row.hiddenrow { opacity: .55; }

  /* "Show hidden" toggle in the filter bar */
  .hidebtn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 13px;
    border-radius: 8px; border: 1.5px solid var(--inputbd); background: var(--input);
    color: var(--muted2); font: 600 12px 'DM Sans', sans-serif; cursor: pointer;
    white-space: nowrap; }
  .hidebtn:hover { color: var(--text-hi); border-color: oklch(0.34 0.02 260); }
  .hidebtn.on { color: var(--text-hi); border-color: oklch(0.4 0.08 252);
    background: oklch(0.22 0.05 252); }

  @media (max-width: 720px) {
    .nav, .head, .banner, .stats, .panel { padding-left: 16px; padding-right: 16px; }
    .nav, .head { padding-left: 16px; padding-right: 16px; }
    .banner, .panel, .tracked { margin-left: 16px; margin-right: 16px; }
    .stats { grid-template-columns: 1fr 1fr; }
    .c-loc, .thead .c-loc, .c-upd, .thead .c-upd { display: none; }
  }
</style>
</head>
<body>
<div class="page">
  <div class="nav">
    <span class="brand">JobTracker</span>
    <span class="live"><span class="d"></span><span>Live</span></span>
    <span class="upd" id="upd"></span>
    <span class="upd-status" id="updStatus" hidden></span>
    <button class="refresh" id="refresh"><span class="ic">↻</span><span id="refreshLabel">Refresh</span></button>
  </div>

  <div class="head">
    <h1>Daily Job Postings</h1>
    <p>Tracking new openings across the companies you follow</p>
  </div>

  <div class="banner" id="banner">
    <span class="d"></span>
    <span class="txt" id="bannerTxt"></span>
    <span class="ct" id="bannerCt"></span>
  </div>

  <div class="tracked" id="tracked" style="display:none">
    <button class="tracked-head" id="trackedHead" type="button" aria-expanded="false" aria-controls="trackedRows">
      <span class="tracked-title">★ Following</span>
      <span class="tracked-ct" id="trackedCt"></span>
      <svg class="tracked-caret" id="trackedCaret" width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"></path></svg>
    </button>
    <div id="trackedRows" style="display:none"></div>
  </div>

  <div class="stats">
    <div class="stat"><p class="l">New Today</p><p class="n blue mono" id="stNew">0</p></div>
    <div class="stat"><p class="l">Total Active</p><p class="n mono" id="stTotal">0</p></div>
    <div class="stat"><p class="l">Companies</p><p class="n mono" id="stCos">0</p></div>
    <div class="stat"><p class="l">Remote Roles</p><p class="n mono" id="stRemote">0</p></div>
  </div>

  <div class="panel">
    <div class="filterbar">
      <div class="search">
        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
          stroke-width="2" stroke-linecap="round"><circle cx="9" cy="9" r="6"></circle><line x1="15" y1="15" x2="19" y2="19"></line></svg>
        <input id="search" type="text" placeholder="Search roles, companies, locations…">
      </div>
      <div class="selwrap">
        <select id="company"></select>
        <svg class="caret" width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 4l4 4 4-4" stroke="oklch(0.55 0.04 260)" stroke-width="1.5" stroke-linecap="round"></path></svg>
      </div>
      <div class="selwrap">
        <select id="loc">
          <option value="all">All Locations</option>
          <option value="remote">Remote</option>
          <option value="onsite">On-site</option>
        </select>
        <svg class="caret" width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 4l4 4 4-4" stroke="oklch(0.55 0.04 260)" stroke-width="1.5" stroke-linecap="round"></path></svg>
      </div>
      <button class="hidebtn" id="hideToggle" type="button" style="display:none"></button>
    </div>

    <div class="thead">
      <div class="c-logo"></div>
      <div class="h c-role">Role</div>
      <div class="h c-status">Status</div>
      <div class="h c-loc">Location</div>
      <div class="h c-upd">Updated</div>
      <div class="c-view"></div>
      <div class="c-act"></div>
    </div>

    <div id="rows"></div>
    <div class="empty" id="empty" style="display:none">No jobs match your current filters.</div>
  </div>
</div>

<script type="application/json" id="data">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById("data").textContent);
const $ = (id) => document.getElementById(id);
const TOKEN = DATA.logo_token;
const COLORS = ["#6f9bff","#8b6fff","#ff6f91","#ffa14a","#34d399","#22b8cf","#e879f9"];
const esc = (s) => (s||"").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));

// Header / stats
// generated_at is an ISO-8601 UTC instant; format it in the viewer's own
// timezone. Fall back to the raw value if it's ever not a parseable date.
function fmtUpdated(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}
$("upd").textContent = "Updated " + fmtUpdated(DATA.generated_at);

// Show whether the latest update completed cleanly.
(function () {
  const s = $("updStatus");
  if (DATA.update_ok) {
    s.textContent = "✓";              // ✓
    s.className = "upd-status ok";
    s.title = "Last update completed successfully";
  } else {
    s.textContent = "!";
    s.className = "upd-status warn";
    const errs = DATA.update_errors || [];
    s.title = "Last update had problems:\n" + (errs.length ? errs.join("\n") : "see logs");
  }
  s.hidden = false;
})();
$("stNew").textContent = DATA.new_count;
$("stTotal").textContent = DATA.total_jobs;
$("stCos").textContent = DATA.companies.length;
$("stRemote").textContent = DATA.remote_count;

// Banner
const banner = $("banner");
if (DATA.new_count > 0) {
  banner.classList.add("has");
  $("bannerTxt").textContent = DATA.new_count + (DATA.new_count === 1 ? " new role" : " new roles") + " discovered in today's run";
} else {
  banner.classList.add("none");
  $("bannerTxt").textContent = "You're all caught up — no new roles since the last run";
}

// Company filter
const sel = $("company");
sel.innerHTML = `<option value="">All Companies</option>` +
  DATA.companies.map(c => `<option value="${esc(c.company)}">${esc(c.company)} (${c.count})</option>`).join("");

function colorFor(name) {
  let h = 0; for (const ch of name) h = (h*31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}
function iniHtml(company) {
  const ini = esc(company.slice(0,2).toUpperCase());
  return `<span class="ini" style="background:${colorFor(company)}">${ini}</span>`;
}
function logoFail(img) { img.parentNode.innerHTML = iniHtml(img.getAttribute("data-co") || "?"); }
function logoHtml(company, domain) {
  if (TOKEN && domain) {
    const src = `https://img.logo.dev/${encodeURIComponent(domain)}?token=${encodeURIComponent(TOKEN)}&size=72&format=png&retina=true`;
    return `<span class="logo"><img src="${src}" alt="${esc(company)}" data-co="${esc(company)}" loading="lazy" onerror="logoFail(this)"></span>`;
  }
  return `<span class="logo">${iniHtml(company)}</span>`;
}

// ---- Persistent per-user state (survives every dashboard rebuild) -----------
// Followed/dismissed roles are saved server-side (data/preferences.json) when a
// live server (serve.py) is actually answering, so they sync across
// browsers/machines. On a static host (GitHub Pages) or over file:// there's no
// server, so we fall back to per-browser localStorage. We feature-detect the
// API rather than trusting the protocol: GitHub Pages is https:// but has no
// backend. Tracked roles are stored as full snapshots so a followed job can
// still be shown after it disappears from the live feed ("no longer available").
let serverPrefs = false;   // set true only once /api/prefs answers
const LS_TRACK = "jt_tracked_v1";   // { [id]: jobSnapshot }
const LS_HIDE  = "jt_hidden_v1";    // [ id, ... ]
function lsGet(k, def) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? def; } catch { return def; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }

// Seed from the prefs embedded at build time so the first paint is correct;
// initPrefs() then reconciles with the freshest source below.
let tracked = (DATA.prefs && DATA.prefs.tracked) || {};
let hidden = new Set((DATA.prefs && DATA.prefs.hidden) || []);
let showHidden = false;

// Following panel starts collapsed to a one-line summary; the "no longer
// available" roles within it stay collapsed even when the panel is expanded.
let trackedExpanded = false;
let goneExpanded = false;

// Jobs present in the current run, by id → used to detect tracked roles that
// have since vanished, and to refresh stored snapshots with the latest data.
const byId = new Map(DATA.jobs.map(j => [j.id, j]));

// Persist the current state to its backing store (live server if one answered,
// otherwise per-browser localStorage).
function persist() {
  if (serverPrefs) {
    fetch("/api/prefs", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracked, hidden: [...hidden] }) }).catch(() => {});
  } else {
    lsSet(LS_TRACK, tracked);
    lsSet(LS_HIDE, [...hidden]);
  }
}

// Load the authoritative state, refresh live snapshots, then do the first paint.
async function initPrefs() {
  if (location.protocol.startsWith("http")) {
    try {
      const r = await fetch("/api/prefs");
      if (r.ok) { const p = await r.json();
        tracked = p.tracked || {}; hidden = new Set(p.hidden || []);
        serverPrefs = true; }
    } catch {}
  }
  if (!serverPrefs) {  // static host (GitHub Pages) or file:// → local fallback
    const t = lsGet(LS_TRACK, null), h = lsGet(LS_HIDE, null);
    if (t) tracked = t;
    if (h) hidden = new Set(h);
  }
  // Keep snapshots of still-live tracked roles current with the latest fetch.
  let dirty = false;
  for (const id of Object.keys(tracked)) {
    if (byId.has(id)) { tracked[id] = byId.get(id); dirty = true; }
  }
  if (dirty) persist();
  render();
}

function toggleTrack(id) {
  if (tracked[id]) delete tracked[id];
  else { const j = byId.get(id) || tracked[id]; if (j) tracked[id] = j; }
  persist();
  renderAll();
}
function toggleHide(id) {
  if (hidden.has(id)) hidden.delete(id); else hidden.add(id);
  persist();
  renderAll();
}
// One delegated listener handles every row's track / dismiss button.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.getAttribute("data-id");
  if (btn.dataset.act === "track") toggleTrack(id);
  else if (btn.dataset.act === "hide") toggleHide(id);
});
// Following-panel collapse/expand and the "no longer available" sub-toggle.
document.addEventListener("click", (e) => {
  if (e.target.closest("#trackedHead")) { trackedExpanded = !trackedExpanded; renderTracked(); return; }
  if (e.target.closest("#goneToggle")) { goneExpanded = !goneExpanded; renderTracked(); }
});

function actionsHtml(j, ctx) {
  const isTracked = !!tracked[j.id];
  const star = `<button class="iconbtn track${isTracked ? " on" : ""}" data-act="track" data-id="${esc(j.id)}" title="${isTracked ? "Stop following" : "Follow this role"}" aria-label="${isTracked ? "Stop following" : "Follow this role"}">${isTracked ? "★" : "☆"}</button>`;
  if (ctx === "tracked") return `<div class="acts">${star}</div>`;
  const isHidden = hidden.has(j.id);
  const drop = `<button class="iconbtn drop" data-act="hide" data-id="${esc(j.id)}" title="${isHidden ? "Restore to list" : "Not interested — hide this role"}" aria-label="${isHidden ? "Restore to list" : "Not interested"}">${isHidden ? "↩" : "✕"}</button>`;
  return `<div class="acts">${star}${drop}</div>`;
}

function rowHtml(j, ctx) {
  const gone = ctx === "tracked" && !byId.has(j.id);
  const badge = gone ? `<div class="badge gone">GONE</div>`
    : (j.isNew ? `<div class="badge">NEW</div>` : "");
  const chipCls = j.remote ? "chip remote" : "chip onsite";
  const loc = j.location ? `<div class="${chipCls}" title="${esc(j.location)}">${esc(j.location)}</div>` : "";
  const view = j.url ? `<a class="view" href="${esc(j.url)}" target="_blank" rel="noopener">View →</a>` : `<span class="c-view"></span>`;
  const cls = "row" + (gone ? " gone" : (j.isNew ? " new" : ""))
    + (ctx === "main" && hidden.has(j.id) ? " hiddenrow" : "");
  const upd = gone ? "no longer listed" : (j.updated || "—");
  return `<div class="${cls}">
    <div class="c-logo">${logoHtml(j.company, j.domain)}</div>
    <div class="c-role"><div class="title">${esc(j.title)}</div><div class="co">${esc(j.company)}</div></div>
    <div class="c-status">${badge}</div>
    <div class="c-loc">${loc}</div>
    <div class="c-upd upd">${esc(upd)}</div>
    ${view}
    <div class="c-act">${actionsHtml(j, ctx)}</div>
  </div>`;
}

function renderTracked() {
  const items = Object.values(tracked);
  const panel = $("tracked");
  if (!items.length) { panel.style.display = "none"; return; }
  // Vanished roles float to the top so they catch the eye; then newest-first.
  items.sort((a, b) => (byId.has(b.id) ? 0 : 1) - (byId.has(a.id) ? 0 : 1)
    || (Number(b.isNew) - Number(a.isNew))
    || a.company.localeCompare(b.company));
  const liveItems = items.filter(j => byId.has(j.id));
  const goneItems = items.filter(j => !byId.has(j.id));
  panel.style.display = "block";
  $("trackedCt").textContent = items.length + (items.length === 1 ? " role" : " roles")
    + (goneItems.length ? ` · ${goneItems.length} no longer available` : "");

  $("trackedHead").setAttribute("aria-expanded", String(trackedExpanded));
  $("trackedCaret").classList.toggle("open", trackedExpanded);
  const rowsEl = $("trackedRows");
  rowsEl.style.display = trackedExpanded ? "block" : "none";
  if (!trackedExpanded) return;   // collapsed: skip rebuilding the (hidden) row HTML

  const goneHtml = goneItems.length
    ? `<button class="gone-toggle" id="goneToggle" type="button" aria-expanded="${goneExpanded}" aria-controls="trackedRows">
        <span>${goneItems.length} no longer available</span>
        <svg class="car${goneExpanded ? " open" : ""}" width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"></path></svg>
      </button>${goneExpanded ? goneItems.map(j => rowHtml(j, "tracked")).join("") : ""}`
    : "";
  rowsEl.innerHTML = liveItems.map(j => rowHtml(j, "tracked")).join("") + goneHtml;
}

function render() {
  renderTracked();
  const q = $("search").value.trim().toLowerCase();
  const co = sel.value;
  const lf = $("loc").value;
  const rows = DATA.jobs.filter(j => {
    if (tracked[j.id]) return false;                 // shown in the Following panel
    if (!showHidden && hidden.has(j.id)) return false;
    if (showHidden && !hidden.has(j.id)) return false;
    if (co && j.company !== co) return false;
    if (lf === "remote" && !j.remote) return false;
    if (lf === "onsite" && j.remote) return false;
    if (q && !(j.title + " " + j.company + " " + j.location).toLowerCase().includes(q)) return false;
    return true;
  });
  $("bannerCt").textContent = rows.length + " of " + DATA.total_jobs + " jobs";
  $("rows").innerHTML = rows.map(j => rowHtml(j, "main")).join("");
  const emptyEl = $("empty");
  emptyEl.style.display = rows.length ? "none" : "block";
  emptyEl.textContent = showHidden
    ? "Nothing hidden yet — use ✕ on a role to mark it as not interested."
    : "No jobs match your current filters.";

  // "Show hidden" toggle reflects the current count.
  const hb = $("hideToggle");
  if (hidden.size) {
    hb.style.display = "inline-flex";
    hb.classList.toggle("on", showHidden);
    hb.textContent = (showHidden ? "Hide dismissed · " : "Show dismissed · ") + hidden.size;
  } else {
    hb.style.display = "none";
    showHidden = false;
  }
}
const renderAll = render;
$("hideToggle").addEventListener("click", () => { showHidden = !showHidden; render(); });
$("search").addEventListener("input", render);
sel.addEventListener("change", render);
$("loc").addEventListener("change", render);

// Refresh: over HTTP via serve.py it triggers a real re-fetch, then reloads.
// On a static host (GitHub Pages) or file://, there's no backend to re-scrape,
// so it just reloads the latest published page instead of reporting a failure.
$("refresh").addEventListener("click", async () => {
  const b = $("refresh");
  if (b.classList.contains("busy")) return;
  b.classList.add("busy"); $("refreshLabel").textContent = "Refreshing…";
  if (location.protocol.startsWith("http")) {
    try {
      const r = await fetch("/api/refresh", { method: "POST" });
      // No backend on this host (e.g. GitHub Pages): the endpoint doesn't
      // exist, so just reload the published page rather than showing a failure.
      if (r.status === 404 || r.status === 405) { location.reload(); return; }
      if (!r.ok) throw new Error(r.status);
    } catch (e) {
      $("refreshLabel").textContent = "Refresh failed";
      b.classList.remove("busy");
      return;
    }
  } else {
    await new Promise(res => setTimeout(res, 400));
  }
  location.reload();
});

initPrefs();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    from scraper.env import load_env
    load_env(root / ".env")
    out = build_dashboard(root / "data", root / "dashboard.html",
                          root / "config.json")
    print(f"dashboard written to {out}")
