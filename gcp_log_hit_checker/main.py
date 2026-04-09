import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import logging as gcp_logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

EMOJI = {"hit": "✅", "no_hit": "❌", "error": "⚠️ ", "cancelled": "⏸️"}


def parse_duration(s: str) -> timedelta:
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    if not s or s[-1] not in units or not s[:-1].isdigit():
        raise argparse.ArgumentTypeError(f"Invalid duration '{s}'. Use e.g. 30d, 7h, 1w, 90m.")
    return timedelta(**{units[s[-1]]: int(s[:-1])})


def entry_link(project: str, insert_id: str) -> str:
    query = quote(f'insertId="{insert_id}"', safe="")
    return f"https://console.cloud.google.com/logs/query;query={query}?project={project}"


def filter_link(project: str, pattern: str, since: timedelta) -> str:
    total_seconds = int(since.total_seconds())
    duration = f"P{total_seconds // 86400}D" if total_seconds % 86400 == 0 else f"PT{total_seconds}S"
    query = quote(pattern, safe="")
    return f"https://console.cloud.google.com/logs/query;query={query};duration={duration}?project={project}"


def check_pattern(client: gcp_logging.Client, pattern: str, freshness_filter: str) -> tuple[str, str, str]:
    """Returns (status, timestamp, entry_link) where status is 'hit' or 'no_hit'."""
    full_filter = f"{pattern} {freshness_filter}"

    entries = client.list_entries(
        filter_=full_filter,
        order_by="timestamp desc",
        max_results=1,
    )
    entry = next(iter(entries), None)
    if entry is None:
        return "no_hit", "", ""
    link = entry_link(client.project, entry.insert_id) if entry.insert_id else ""
    return "hit", str(entry.timestamp), link


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="File with log filter patterns, one per line")
    parser.add_argument("--project", help="GCP project ID (defaults to gcloud config project)")
    parser.add_argument(
        "--since",
        default="30d",
        type=parse_duration,
        metavar="DURATION",
        help="How far back to search (e.g. 30d, 7h, 1w, 90m). Default: 30d",
    )
    parser.add_argument(
        "--format",
        choices=["tsv", "json"],
        default="tsv",
        help="Output format. Default: tsv",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600,
        metavar="SECONDS",
        help="Total timeout in seconds for all checks. Default: 600",
    )
    args = parser.parse_args()

    freshness_filter = (datetime.now(timezone.utc) - args.since).strftime('timestamp>="%Y-%m-%dT%H:%M:%SZ"')

    file_path = args.file
    try:
        with open(file_path) as f:
            patterns = [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]
    except OSError as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    client = gcp_logging.Client(project=args.project)
    print(f"Using project: {client.project}", file=sys.stderr)

    results: dict[int, tuple[str, str, str]] = {}

    with Progress(
        TimeElapsedColumn(),
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=Console(stderr=True),
    ) as progress:
        overall = progress.add_task(f"[bold]0/{len(patterns)} done[/bold]", total=len(patterns))
        task_ids = {i: progress.add_task(f"[dim]{pattern}[/dim]", total=1) for i, pattern in enumerate(patterns)}

        interrupted = False
        pool = ThreadPoolExecutor(max_workers=10)
        try:
            futures = {pool.submit(check_pattern, client, p, freshness_filter): (i, p) for i, p in enumerate(patterns)}
            for completed, future in enumerate(as_completed(futures, timeout=args.timeout), 1):
                i, pattern = futures[future]
                error_msg = None
                try:
                    status, timestamp, link = future.result()
                    results[i] = (status, timestamp, link)
                except GoogleAPICallError as e:
                    error_msg = f"API error: {e}"
                    results[i] = ("error", error_msg, "")
                except Exception as e:
                    error_msg = f"Error: {e}"
                    results[i] = ("error", error_msg, "")

                status, *_ = results[i]
                progress.update(
                    task_ids[i],
                    description=f"{EMOJI[status]} [dim]{pattern}[/dim]",
                    completed=1,
                )
                if error_msg:
                    progress.add_task(f"  [red]{error_msg}[/red]", total=1, completed=1)
                progress.update(
                    overall,
                    description=f"[bold]{completed}/{len(patterns)} done[/bold]",
                    completed=completed,
                )
        except FuturesTimeoutError:
            print(
                f"Timed out after {args.timeout}s — some patterns did not complete.",
                file=sys.stderr,
            )
            pool.shutdown(wait=False, cancel_futures=True)
        except KeyboardInterrupt:
            interrupted = True
            pool.shutdown(wait=False, cancel_futures=True)

    if interrupted:
        print("--- Results (interrupted) ---", file=sys.stderr)
    else:
        print("--- Results ---", file=sys.stderr)

    if args.format == "json":
        output = []
        for i, pattern in enumerate(patterns):
            if i not in results:
                output.append(
                    {
                        "pattern": pattern,
                        "status": "cancelled",
                        "timestamp": None,
                        "entry_link": None,
                        "filter_link": filter_link(client.project, pattern, args.since),
                    }
                )
            else:
                status, timestamp, link = results[i]
                if status == "error":
                    print(f"⚠️  {pattern}: {timestamp}", file=sys.stderr)
                    continue
                output.append(
                    {
                        "pattern": pattern,
                        "status": status,
                        "timestamp": timestamp or None,
                        "entry_link": link or None,
                        "filter_link": filter_link(client.project, pattern, args.since),
                    }
                )
        print(json.dumps(output, indent=2))
    else:
        for i, pattern in enumerate(patterns):
            flink = filter_link(client.project, pattern, args.since)
            if i not in results:
                print(f"{EMOJI['cancelled']}\t{pattern}\t\t\t{flink}")
                continue
            status, timestamp, link = results[i]
            if status == "error":
                print(f"⚠️  {pattern}: {timestamp}", file=sys.stderr)
                continue
            print(f"{EMOJI[status]}\t{pattern}\t{timestamp}\t{link}\t{flink}")

    # Force-exit to kill any threads still blocked on network calls
    os._exit(130 if interrupted else 0)


if __name__ == "__main__":
    main()
