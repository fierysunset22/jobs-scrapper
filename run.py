#!/usr/bin/env python3
"""Nightly job-posting tracker.

Fetches open roles for every company in config.json, diffs each against the
previous run, and reports newly-posted roles via a Markdown digest (and email,
if configured).

Usage:
    python3 run.py                 # fetch, diff, notify, save state
    python3 run.py --seed          # save current state without reporting anything
    python3 run.py --config other.json --data-dir /path/to/data
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from datetime import date

from scraper import adapters, store
from scraper.dashboard import build_dashboard
from scraper.env import load_env
from scraper.filters import make_filter
from scraper.notify import notify

ROOT = Path(__file__).resolve().parent
load_env(ROOT / ".env")


def load_config(path: Path) -> tuple[list[dict], dict]:
    with path.open(encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["companies"], cfg.get("filters", {})


def run(config_path: Path, data_dir: Path, seed: bool) -> int:
    companies, filter_cfg = load_config(config_path)
    keep = make_filter(filter_cfg)
    run_date = date.today().isoformat()
    results = []

    for cfg in companies:
        name = cfg["company"]
        result = {"company": name, "new": [], "removed": [],
                  "seeded": False, "error": None}
        try:
            raw = adapters.fetch(cfg)
            jobs = [j for j in raw if keep(j)]
            print(f"[fetch] {name}: {len(raw)} open roles "
                  f"→ {len(jobs)} after filter")

            if seed:
                result["seeded"] = True
            else:
                previous = store.load_snapshot(data_dir, name)
                d = store.diff(previous, jobs)
                result.update(seeded=d["seeded"], new=d["new"],
                              removed=d["removed"])
                if d["seeded"]:
                    print(f"[diff]  {name}: seeded (first run)")
                else:
                    print(f"[diff]  {name}: +{len(d['new'])} new, "
                          f"-{len(d['removed'])} removed")
                    store.record_events(data_dir, name, d["new"], run_date)

            store.save_snapshot(data_dir, name, jobs)
        except adapters.FetchError as exc:
            result["error"] = str(exc)
            print(f"[error] {name}: {exc}", file=sys.stderr)

        results.append(result)
        time.sleep(1)  # be a polite API citizen between companies

    notify(data_dir, results)

    # Record the run outcome (drives the dashboard's "update succeeded" badge)
    # before regenerating the page, so collect() picks up the fresh status.
    errors = [f"{r['company']}: {r['error']}" for r in results if r["error"]]
    store.save_run_status(data_dir, ok=not errors, errors=errors)

    out = build_dashboard(data_dir, ROOT / "dashboard" / "index.html", config_path)
    print(f"[dashboard] {out}")
    return 1 if errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.json"),
                        help="path to config.json")
    parser.add_argument("--data-dir", default=str(ROOT / "data"),
                        help="where state snapshots and digests are stored")
    parser.add_argument("--seed", action="store_true",
                        help="save current state without reporting new jobs")
    args = parser.parse_args()

    sys.exit(run(Path(args.config), Path(args.data_dir), args.seed))


if __name__ == "__main__":
    main()
