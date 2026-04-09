# gcp-log-hit-checker

[![PyPI version](https://img.shields.io/pypi/v/gcp-log-hit-checker)](https://pypi.org/project/gcp-log-hit-checker/)
[![Python versions](https://img.shields.io/pypi/pyversions/gcp-log-hit-checker)](https://pypi.org/project/gcp-log-hit-checker/)
[![PyPI downloads](https://img.shields.io/pypi/dm/gcp-log-hit-checker)](https://pypi.org/project/gcp-log-hit-checker/)

Checks a list of GCP Cloud Logging filter patterns and reports whether each had any hits in the last 30 days. Patterns are checked in parallel and results are printed as tab-separated values to stdout.

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
gcp-log-hit-checker <patterns-file> [--project <gcp-project-id>] [--since <duration>]
```

- `--project` — GCP project ID, defaults to your active `gcloud` config project
- `--since` — how far back to search; accepts `m` (minutes), `h` (hours), `d` (days), `w` (weeks). Default: `30d`

## Patterns file

One [Cloud Logging filter](https://cloud.google.com/logging/docs/view/logging-query-language) per line. Lines starting with `#` are ignored.

```
# Check specific endpoints
httpRequest.requestUrl=~"api/v1/.*/orders"
severity=ERROR resource.type="gce_instance"
```

## Output

Tab-separated to stdout: `<emoji>\t<pattern>\t<last-hit-timestamp>`

```
✅	httpRequest.requestUrl=~"api/v1/.*/orders"	2026-01-15 10:23:45+00:00
❌	severity=ERROR resource.type="gce_instance"
```

`Ctrl+C` prints a partial summary of completed checks before exiting.
