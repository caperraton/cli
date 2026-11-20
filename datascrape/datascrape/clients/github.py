import re
from typing import Any, Dict, List, Optional
from datascrape.clients.base import VCSClient
from datascrape.http_client import ResilientHTTPClient

SERVICE_REGEX = re.compile(
    r"(bot|svc|srv|service|sa_|sa-|ci-|cd-|deploy|automation|machine)", re.IGNORECASE
)
CI_FILES = [
    (".github/workflows", "github_actions"),
    ("Jenkinsfile", "jenkins"),
    ("azure-pipelines.yml", "azure_pipelines"),
    (".circleci/config.yml", "circleci"),
]


class GitHubClient(VCSClient):
    def __init__(self, deployment_type: str, base_url: str, token: str, org_or_project: str, verify_ssl: bool = True):
        api_url = "https://api.github.com" if deployment_type == "cloud" else f"{base_url.rstrip('/')}/api/v3"
        super().__init__("github", deployment_type, api_url, token, org_or_project, verify_ssl)
        self.http = ResilientHTTPClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            verify_ssl=verify_ssl,
        )

    def _paginate(self, url: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        results: List[Any] = []
        next_url: Optional[str] = url
        next_params = dict(params or {})
        while next_url:
            resp = self.http.request("GET", next_url, params=next_params)
            if not resp:
                break
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
            next_url = resp.links.get("next", {}).get("url")
            next_params = {}  # next_url already includes query params
        return results

    def list_repos(self) -> List[Dict[str, Any]]:
        raw = self._paginate(f"{self.base_url}/orgs/{self.org_or_project}/repos", {"type": "all", "per_page": 100})
        return [
            {
                "platform": self.platform,
                "deployment_type": self.deployment_type,
                "org": self.org_or_project,
                "name": r["name"],
                "full_name": r["full_name"],
                "archived": bool(r.get("archived")),
                "pushed_at": r.get("pushed_at"),
                "size_kb": int(r.get("size") or 0),
                "html_url": r.get("html_url", ""),
            }
            for r in raw
        ]

    def _path_exists(self, full_name: str, path: str) -> bool:
        resp = self.http.request("GET", f"{self.base_url}/repos/{full_name}/contents/{path}", allow_404=True)
        return resp is not None

    def check_owner_and_ci(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        full_name = repo["full_name"]
        has_codeowners = any(
            self._path_exists(full_name, p)
            for p in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
        )
        ci_types = [label for path, label in CI_FILES if self._path_exists(full_name, path)]
        return {
            "has_codeowners": has_codeowners,
            "has_ci": bool(ci_types),
            "ci_type": ",".join(ci_types) if ci_types else "none",
        }

    def list_apps_and_service_accounts(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        # 1. GitHub App Installations
        try:
            pages = self._paginate(f"{self.base_url}/orgs/{self.org_or_project}/installations", {"per_page": 100})
            for page in pages:
                for inst in page.get("installations", []):
                    rows.append({
                        "platform": self.platform,
                        "org": self.org_or_project,
                        "record_type": "github_app",
                        "identifier": inst.get("app_slug") or str(inst.get("app_id")),
                        "scope": inst.get("repository_selection", ""),
                        "updated_at": inst.get("updated_at", ""),
                        "owner": "",
                    })
        except Exception as exc:
            print(f"[warn] Could not fetch app installations for {self.org_or_project}: {exc}")

        # 2. Org Members & Outside Collaborators (service-account heuristic)
        for endpoint, source_type in (("members", "org_member"), ("outside_collaborators", "outside_collaborator")):
            try:
                users = self._paginate(f"{self.base_url}/orgs/{self.org_or_project}/{endpoint}", {"per_page": 100})
                for u in users:
                    login = u.get("login", "")
                    if SERVICE_REGEX.search(login) or u.get("type") == "Bot":
                        rows.append({
                            "platform": self.platform,
                            "org": self.org_or_project,
                            "record_type": f"service_account_candidate:{source_type}",
                            "identifier": login,
                            "scope": u.get("type", ""),
                            "updated_at": "",
                            "owner": "",
                        })
            except Exception as exc:
                print(f"[warn] Could not fetch {endpoint} for {self.org_or_project}: {exc}")
        return rows

    def list_pull_requests(
        self, repo: Dict[str, Any], since: Optional[str] = None, until: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        full_name = repo["full_name"]
        prs = self._paginate(
            f"{self.base_url}/repos/{full_name}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
        )
        rows: List[Dict[str, Any]] = []
        for pr in prs:
            created = pr.get("created_at") or ""
            if since and created < since:
                continue
            if until and created > until:
                continue
            rows.append({
                "platform": self.platform,
                "org": self.org_or_project,
                "repo": repo["name"],
                "pr_id": str(pr.get("number")),
                "state": pr.get("state", ""),
                "author": (pr.get("user") or {}).get("login", ""),
                "created_at": created,
                "merged_at": pr.get("merged_at") or "",
                "closed_at": pr.get("closed_at") or "",
            })
        return rows