from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from datascrape.clients.base import VCSClient


def chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), max(1, size)):
        yield items[i : i + max(1, size)]


def run_chunked(
    items: List[Any],
    worker_fn: Callable[[Any], Any],
    workers: int,
    chunk_size: int,
) -> Tuple[List[Any], List[Dict[str, str]]]:
    results: List[Any] = []
    errors: List[Dict[str, str]] = []
    for batch in chunked(items, chunk_size):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(worker_fn, item): item for item in batch}
            for fut in as_completed(future_map):
                item = future_map[fut]
                try:
                    res = fut.result()
                    if isinstance(res, list):
                        results.extend(res)
                    elif res is not None:
                        results.append(res)
                except Exception as exc:
                    errors.append({"item": str(item.get("full_name", item)), "error": str(exc)})
    return results, errors


def run_report(
    clients: List[VCSClient],
    report_type: str,
    workers: int = 8,
    chunk_size: int = 50,
    inactive_days: int = 180,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], List[str]]:
    all_rows: List[Dict[str, Any]] = []
    all_errors: List[Dict[str, str]] = []

    for client in clients:
        print(f"[run] {client.platform} ({client.deployment_type}) -> {client.org_or_project} [{report_type}]")
        if report_type == "apps_service_accounts":
            all_rows.extend(client.list_apps_and_service_accounts())
            continue

        repos = client.list_repos()

        if report_type == "ownership_baseline":
            active = [r for r in repos if not r["archived"]]

            def _inspect_repo(r: Dict[str, Any]) -> Dict[str, Any]:
                info = client.check_owner_and_ci(r)
                return {**r, **info}

            rows, errs = run_chunked(active, _inspect_repo, workers, chunk_size)
            all_rows.extend(rows)
            all_errors.extend(errs)

        elif report_type == "archived_inactive":
            now = datetime.now(timezone.utc)
            for r in repos:
                days = None
                if r.get("pushed_at"):
                    dt = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
                    days = (now - dt).days
                is_inactive = (not r["archived"]) and (days is None or days >= inactive_days)
                if not r["archived"] and not is_inactive:
                    continue
                disp = (
                    "Retain Archived / Audit for Purge"
                    if r["archived"]
                    else ("Propose Archive (12+ mo)" if (days or 9999) >= 365 else "Verify Ownership / Archive")
                )
                all_rows.append({
                    **r,
                    "days_since_push": days if days is not None else "never",
                    "size_mb": round(r["size_kb"] / 1024, 2),
                    "proposed_disposition": disp,
                })

        elif report_type == "pull_request_metrics":
            def _fetch_prs(r: Dict[str, Any]) -> List[Dict[str, Any]]:
                return client.list_pull_requests(r, since=since, until=until)

            rows, errs = run_chunked(repos, _fetch_prs, workers, chunk_size)
            all_rows.extend(rows)
            all_errors.extend(errs)
        else:
            raise ValueError(f"Unknown report_type: {report_type}")

    key_map = {
        "ownership_baseline": ["platform", "org", "full_name"],
        "apps_service_accounts": ["platform", "org", "record_type", "identifier"],
        "archived_inactive": ["platform", "org", "full_name"],
        "pull_request_metrics": ["platform", "org", "repo", "pr_id"],
    }
    return all_rows, all_errors, key_map[report_type]