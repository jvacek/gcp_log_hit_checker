import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import logging as gcp_logging
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

freshness_filter = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
    'timestamp>="%Y-%m-%dT%H:%M:%SZ"'
)


def check_pattern(client: gcp_logging.Client, pattern: str) -> tuple[bool, str]:
    full_filter = f"{pattern} {freshness_filter}"

    print(f"  filter: {full_filter!r}", file=sys.stderr)
    entries = client.list_entries(
        filter_=full_filter,
        order_by="timestamp desc",
        max_results=1,
    )
    entry = next(iter(entries), None)
    if entry is None:
        return False, ""
    return True, str(entry.timestamp)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="File with log filter patterns, one per line")
    parser.add_argument(
        "--project", help="GCP project ID (defaults to gcloud config project)"
    )
    args = parser.parse_args()

    file_path = args.file
    try:
        with open(file_path) as f:
            patterns = [
                line.strip()
                for line in f
                if line.strip() and not line.lstrip().startswith("#")
            ]
    except OSError as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    client = gcp_logging.Client(project=args.project)
    print(f"Using project: {client.project}", file=sys.stderr)

    results: dict[int, tuple[str, str]] = {}

    with Progress(
        TimeElapsedColumn(),
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        overall = progress.add_task(
            f"[bold]0/{len(patterns)} done[/bold]", total=len(patterns)
        )
        task_ids = {
            i: progress.add_task(f"[dim]{pattern}[/dim]", total=1)
            for i, pattern in enumerate(patterns)
        }

        interrupted = False
        try:
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = {
                    pool.submit(check_pattern, client, p): (i, p)
                    for i, p in enumerate(patterns)
                }
                for completed, future in enumerate(as_completed(futures), 1):
                    i, pattern = futures[future]
                    error_msg = None
                    try:
                        has_hits, timestamp = future.result()
                        emoji = "✅" if has_hits else "❌"
                        results[i] = (emoji, timestamp)
                    except GoogleAPICallError as e:
                        error_msg = f"API error: {e}"
                        results[i] = ("⚠️ ", error_msg)
                    except Exception as e:
                        error_msg = f"Error: {e}"
                        results[i] = ("⚠️ ", error_msg)

                    emoji, _ = results[i]
                    progress.update(
                        task_ids[i],
                        description=f"{emoji} [dim]{pattern}[/dim]",
                        completed=1,
                    )
                    if error_msg:
                        progress.add_task(
                            f"  [red]{error_msg}[/red]", total=1, completed=1
                        )
                    progress.update(
                        overall,
                        description=f"[bold]{completed}/{len(patterns)} done[/bold]",
                        completed=completed,
                    )
        except KeyboardInterrupt:
            interrupted = True
            for future in futures:
                future.cancel()

    if interrupted:
        print("--- Results (interrupted) ---", file=sys.stderr)
    else:
        print("--- Results ---", file=sys.stderr)

    for i, pattern in enumerate(patterns):
        if i not in results:
            continue
        emoji, timestamp = results[i]
        print(f"{emoji}\t{pattern}\t{timestamp}")


if __name__ == "__main__":
    main()
