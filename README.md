# jobs-scrapper

Nightly tracker for new job postings at companies you want to work for. Pulls
open roles straight from each company's ATS JSON API, diffs against the previous
run, and reports only the **newly-posted** roles.

No dependencies — pure Python 3 standard library, so it runs under `launchd`/cron
with no virtualenv or `pip install`.

## How it works

```
config.json ──▶ adapters ──▶ fetch open roles
                                   │
                  data/state/*.json (last run's snapshot)
                                   │
                                 diff ──▶ new postings ──▶ digest + email
```

- **adapters** (`scraper/adapters.py`) — one per ATS, all returning the same
  normalized job shape (`id`, `title`, `location`, `url`, `updated_at`).
- **store** (`scraper/store.py`) — saves a snapshot per company and diffs the
  next fetch against it. First run for a company is a silent *seed* (no flood).
- **notify** (`scraper/notify.py`) — prints a summary, writes a dated Markdown
  digest to `data/digests/`, and optionally emails it.

## Supported providers

| provider    | API (no auth required)                                          |
|-------------|----------------------------------------------------------------|
| `greenhouse`| `boards-api.greenhouse.io/v1/boards/<slug>/jobs`               |
| `lever`     | `api.lever.co/v0/postings/<slug>?mode=json`                    |
| `eightfold` | `<base_url>/api/apply/v2/jobs?domain=<domain>` (paginated)     |
| `ashby`     | `api.ashbyhq.com/posting-api/job-board/<slug>`                  |

## Usage

```bash
python3 run.py            # fetch → diff → notify → save state
python3 run.py --seed     # capture current state silently (no reporting)
python3 run.py --config other.json --data-dir /tmp/jobs   # overrides
```

Exit code is non-zero if any company failed to fetch (handy for cron alerting).
A failed company never aborts the others — its error is recorded in the digest.

## Live dashboard server (optional)

By default `index.html` is a static file: data is baked in when `run.py`
generates it, and its Refresh button only reloads the file. To make Refresh
actually re-fetch live, run the local server instead:

```bash
python3 serve.py            # http://127.0.0.1:8787
```

Open that URL (not the file). The Refresh button now POSTs to `/api/refresh`,
which re-runs the full fetch → diff → regenerate pipeline and reloads with fresh
data. Localhost only; stdlib-only, no dependencies.

## Adding a company

Find the company's ATS and add an entry to `config.json`:

```jsonc
{ "company": "Figma", "provider": "greenhouse", "slug": "figma" }
```

The `slug` is the path segment in the ATS URL. Greenhouse covers most tech
companies; check `boards-api.greenhouse.io/v1/boards/<slug>/jobs` in a browser.
For Eightfold, also provide `domain` and `base_url` (see Netflix in config.json).

## Nightly schedule (macOS, launchd)

```bash
cp com.raul.jobs-scrapper.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.raul.jobs-scrapper.plist
launchctl start com.raul.jobs-scrapper   # run once now to test
```

Runs daily at 07:00. Logs to `data/run.log`. Unload with `launchctl unload …`.

## Email (optional)

Set these in the environment (or in the plist's `EnvironmentVariables` block):

```bash
JOBS_SMTP_HOST=smtp.gmail.com
JOBS_SMTP_PORT=587
JOBS_SMTP_USER=you@gmail.com
JOBS_SMTP_PASS=<Gmail App Password, not your login password>
JOBS_SMTP_TO=you@gmail.com
```

Without these, the digest is still written to `data/digests/` and printed.

## Notes

- `data/` (snapshots, digests, logs) is gitignored — it's local run state.
- Be a polite API citizen: the runner sleeps 1s between companies. These are
  public endpoints with no documented rate limits, but don't hammer them.
