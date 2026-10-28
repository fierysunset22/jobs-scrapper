"""State persistence and diffing.

Each company gets one JSON file under ``data/state/<company>.json`` holding the
full set of jobs seen on the last run, keyed by job id. Comparing today's fetch
against that snapshot yields the new (and removed) postings.

The first time a company is seen there is no prior snapshot, so *every* job
would look new. To avoid flooding the first digest, the first run is treated as
a silent "seed": the snapshot is saved and no jobs are reported as new.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_DIRNAME = "state"


def _state_path(data_dir: Path, company: str) -> Path:
    safe = company.lower().replace("/", "-").replace(" ", "-")
    return data_dir / STATE_DIRNAME / f"{safe}.json"


def load_snapshot(data_dir: Path, company: str) -> dict | None:
    """Return {job_id: job} from the last run, or None if never seen."""
    path = _state_path(data_dir, company)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(data_dir: Path, company: str, jobs: list[dict]) -> None:
    path = _state_path(data_dir, company)
    path.parent.mkdir(parents=True, exist_ok=True)

    previous = load_snapshot(data_dir, company) or {}
    snapshot = {}
    for j in jobs:
        job_id = j["id"]
        job = dict(j)
        if job_id in previous:
            prev_job = previous[job_id]
            if "first_seen" in prev_job:
                job.setdefault("first_seen", prev_job["first_seen"])
        else:
            job.setdefault("first_seen", datetime.now(timezone.utc).date().isoformat())
        snapshot[job_id] = job

    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    tmp.replace(path)  # atomic: a crash mid-write never corrupts the snapshot


def _events_path(data_dir: Path) -> Path:
    return data_dir / "events.json"


def load_events(data_dir: Path) -> list[dict]:
    """Return the full discovery feed (every job the tracker has ever flagged
    as new), oldest first."""
    path = _events_path(data_dir)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def record_events(data_dir: Path, company: str, new_jobs: list[dict],
                  run_date: str) -> None:
    """Append newly-discovered jobs to the persistent discovery feed."""
    if not new_jobs:
        return
    events = load_events(data_dir)
    for j in new_jobs:
        job = dict(j)
        job.setdefault("first_seen", run_date)
        events.append({
            "date": run_date,
            "company": company,
            "id": job["id"],
            "title": job["title"],
            "location": job["location"],
            "url": job["url"],
        })
    path = _events_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _run_status_path(data_dir: Path) -> Path:
    return data_dir / "run_status.json"


def save_run_status(data_dir: Path, ok: bool, errors: list[str]) -> None:
    """Record the outcome of the most recent run so the dashboard can show
    whether the latest update succeeded."""
    path = _run_status_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": ok,
        "errors": errors,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def load_run_status(data_dir: Path) -> dict | None:
    """Return the most recent run's outcome, or None if it was never recorded."""
    path = _run_status_path(data_dir)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def diff(previous: dict | None, jobs: list[dict]) -> dict:
    """Compare a fresh fetch against the previous snapshot.

    Returns a dict with:
        seeded:  True if this was a first run (no prior snapshot)
        new:     jobs present now but not before
        removed: jobs present before but gone now
    """
    if previous is None:
        return {"seeded": True, "new": [], "removed": []}

    current_ids = {j["id"] for j in jobs}
    new = [j for j in jobs if j["id"] not in previous]
    removed = [previous[i] for i in previous if i not in current_ids]
    return {"seeded": False, "new": new, "removed": removed}
