import argparse
import json
from pathlib import Path
from typing import List
from datascrape.clients import build_client
from datascrape.clients.base import VCSClient
from datascrape.reports import run_report
from datascrape.storage import DBManager, export_report


def main() -> None:
    parser = argparse.ArgumentParser(prog="datascrape", description="Multi-VCS inventory & observability CLI")
    parser.add_argument("target", help="github | ghes | bitbucket | combined")
    parser.add_argument("--type", dest="deployment_type", choices=["cloud", "self_hosted"], default="cloud")
    parser.add_argument("--url", default="https://api.github.com", help="Base URL for self-hosted or API")
    parser.add_argument("--token", default="", help="API token")
    parser.add_argument("--org", default="", help="Org / Workspace / Project key")
    parser.add_argument("--config", type=Path, default=None, help="JSON file of multiple targets for combined reports")
    parser.add_argument(
        "--report",
        required=True,
        choices=["ownership_baseline", "apps_service_accounts", "archived_inactive", "pull_request_metrics"],
    )
    parser.add_argument("--output", default="csv,json", help="Comma-delimited: csv,json | csv | json")
    parser.add_argument("--out-dir", type=Path, default=Path("./reports"))
    parser.add_argument("--workers", type=int, default=8, help="Thread pool concurrency")
    parser.add_argument("--chunk-size", type=int, default=50, help="Repos processed per chunk")
    parser.add_argument("--inactive-days", type=int, default=180)
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite DB path to upsert results")
    parser.add_argument("--backfill-since", default=None, help="ISO-8601 start date for PR backfill (e.g. 2026-01-01T00:00:00Z)")
    parser.add_argument("--backfill-until", default=None, help="ISO-8601 end date for PR backfill")
    parser.add_argument("--insecure", action="store_true", help="Disable SSL verification if needed")
    args = parser.parse_args()

    formats = [f.strip().lower() for f in args.output.split(",") if f.strip()]
    clients: List[VCSClient] = []

    if args.target.lower() == "combined":
        if not args.config:
            parser.error("--config is required when target is 'combined'")
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        for entry in cfg:
            clients.append(
                build_client(
                    target=entry["target"],
                    deployment_type=entry["type"],
                    url=entry.get("url", ""),
                    token=entry["token"],
                    org=entry["org"],
                    verify_ssl=not args.insecure,
                )
            )
    else:
        clients.append(
            build_client(
                target=args.target,
                deployment_type=args.deployment_type,
                url=args.url,
                token=args.token,
                org=args.org,
                verify_ssl=not args.insecure,
            )
        )

    rows, errors, key_fields = run_report(
        clients=clients,
        report_type=args.report,
        workers=args.workers,
        chunk_size=args.chunk_size,
        inactive_days=args.inactive_days,
        since=args.backfill_since,
        until=args.backfill_until,
    )

    export_report(rows, args.out_dir, f"{args.target}_{args.report}", formats)
    if errors:
        export_report(errors, args.out_dir, f"{args.target}_{args.report}_errors", ["csv", "json"])

    if args.db_path:
        db = DBManager(args.db_path)
        upserted = db.upsert_rows(args.report, rows, key_fields)
        db.close()
        print(f"[db] Upserted {upserted} rows into {args.db_path}")


if __name__ == "__main__":
    main()