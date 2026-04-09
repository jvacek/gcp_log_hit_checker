# gcp-log-hit-checker

[![PyPI version](https://img.shields.io/pypi/v/gcp-log-hit-checker)](https://pypi.org/project/gcp-log-hit-checker/)
[![Python versions](https://img.shields.io/pypi/pyversions/gcp-log-hit-checker)](https://pypi.org/project/gcp-log-hit-checker/)
[![PyPI downloads](https://img.shields.io/pypi/dm/gcp-log-hit-checker)](https://pypi.org/project/gcp-log-hit-checker/)

Checks a list of GCP Cloud Logging filter patterns and reports whether each had any hits in a configurable time window. Patterns are checked in parallel, progress is shown on stderr, and results are written to stdout.

## Installation

```
uv tool install gcp-log-hit-checker
```

Or with pip:

```
pip install gcp-log-hit-checker
```

## Usage

```
gcp-log-hit-checker <patterns-file> [--project <gcp-project-id>] [--since <duration>] [--format tsv|json] [--timeout <seconds>]
```

- `--project` — GCP project ID, defaults to your active `gcloud` config project
- `--since` — how far back to search; accepts `m` (minutes), `h` (hours), `d` (days), `w` (weeks). Default: `30d`
- `--format` — output format, `tsv` (default) or `json`
- `--timeout` — timeout per pattern check in seconds. Default: `600`

## Patterns file

One [Cloud Logging filter](https://cloud.google.com/logging/docs/view/logging-query-language) per line. Lines starting with `#` are ignored.

```
# Check specific endpoints
httpRequest.requestUrl=~"api/v1/.*/orders"
severity=ERROR resource.type="gce_instance"
```

## Output

Progress and status messages are written to stderr. Results are written to stdout, making it safe to redirect to a file:

```bash
gcp-log-hit-checker patterns.txt > results.tsv
gcp-log-hit-checker --format json patterns.txt > results.json
```

### TSV

Tab-separated columns: `<emoji>\t<pattern>\t<last-hit-timestamp>\t<entry-link>\t<filter-link>`

```
✅	httpRequest.requestUrl=~"api/v1/.*/orders"	2026-01-15 10:23:45+00:00	https://console.cloud.google.com/...	https://console.cloud.google.com/...
❌	severity=ERROR resource.type="gce_instance"			https://console.cloud.google.com/...
```

### JSON

```json
[
  {
    "pattern": "httpRequest.requestUrl=~\"api/v1/.*/orders\"",
    "status": "hit",
    "timestamp": "2026-01-15 10:23:45+00:00",
    "entry_link": "https://console.cloud.google.com/logs/query;query=insertId%3D%22abc123%22?project=my-project",
    "filter_link": "https://console.cloud.google.com/logs/query;query=...;duration=P30D?project=my-project"
  },
  {
    "pattern": "severity=ERROR resource.type=\"gce_instance\"",
    "status": "no_hit",
    "timestamp": null,
    "entry_link": null,
    "filter_link": "https://console.cloud.google.com/logs/query;query=...;duration=P30D?project=my-project"
  }
]
```

Possible `status` values: `hit`, `no_hit`, `error`, `cancelled` (interrupted before check ran).

`Ctrl+C` prints a partial summary of completed checks before exiting.
