from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from datascrape.clients.base import VCSClient
from datascrape.http_client import ResilientHTTPClient


class BitbucketClient(VCSClient):
    def __init__(self, deployment_type: str, base_url: str, token: str, org_or_project: str, verify_ssl: bool = True):
        api_url = (
            "https://api.bitbucket.org/2.0"
            if deployment_type == "cloud"
            else f"{base_url.rstrip('/')}/rest/api/1.0"
        )
        super().__init__("bitbucket", deployment_type, api_url, token, org_or_project, verify_ssl)
        self.http = ResilientHTTPClient(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            verify_ssl=verify_ssl,
        )

    def _paginate_cloud(self, url: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        next_url: Optional[str] = url
        while next_url:
            resp = self.http.request("GET", next_url)
            if not resp:
                break
            data = resp.json()
            items.extend(data.get("values", []))
            next_url = data.get("next")
        return items

    def _paginate_server(self, url: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        start = 0
        while True:
            p = dict(params or {}, start=start, limit=100)
            resp = self.http.request("GET", url, params=p)
            if not resp:
                break
            data = resp.json()
            items.extend(data.get("values", []))
            if data.get("isLastPage", True):
                break
            start = data.get("nextPageStart", start + 100)
        return items

    def list_repos(self) -> List[Dict[str, Any]]:
        if self.deployment_type == "cloud":
            raw = self._paginate_cloud(f"{self.base_url}/repositories/{self.org_or_project}")
            return [
                {
                    "platform": self.platform,
                    "deployment_type": self.deployment_type,
                    "org": self.org_or_project,
                    "name": r["slug"],
                    "full_name": r["full_name"],
                    "archived": False,
                    "pushed_at": r.get("updated_on"),
                    "size_kb": int((r.get("size") or 0) / 1024),
                    "html_url": r.get("links", {}).get("html", {}).get("href", ""),
                }
                for r in raw
            ]
        # On-prem Bitbucket Server / Data Center
        raw = self._paginate_server(f"{self.base_url}/projects/{self.org_or_project}/repos")
        return [
            {
                "platform": self.platform,
                "deployment_type": self.deployment_type,
                "org": self.org_or_project,
                "name": r["slug"],
                "full_name": f"{self.org_or_project}/{r['slug']}",
                "archived": bool(r.get("archived", False)),
                "pushed_at": None,
                "size_kb": 0,
                "html_url": (r.get("links", {}).get("self") or [{}])[0].get("href", ""),
            }
            for r in raw
        ]

    def check_owner_and_ci(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        if self.deployment_type == "cloud":
            base = f"{self.base_url}/repositories/{repo['full_name']}/src/HEAD"
            has_co = self.http.request("GET", f"{base}/CODEOWNERS", allow_404=True) is not None
            has_ci = self.http.request("GET", f"{base}/bitbucket-pipelines.yml", allow_404=True) is not None
            return {"has_codeowners": has_co, "has_ci": has_ci, "ci_type": "bitbucket_pipelines" if has_ci else "none"}

        base = f"{self.base_url}/projects/{self.org_or_project}/repos/{repo['name']}/browse"
        has_co = self.http.request("GET", f"{base}/CODEOWNERS", allow_404=True) is not None
        has_ci = self.http.request("GET", f"{base}/Jenkinsfile", allow_404=True) is not None
        return {"has_codeowners": has_co, "has_ci": has_ci, "ci_type": "jenkins" if has_ci else "none"}

    def list_apps_and_service_accounts(self) -> List[Dict[str, Any]]:
        # Bitbucket Cloud workspace members / On-prem project users
        rows: List[Dict[str, Any]] = []
        if self.deployment_type == "cloud":
            members = self._paginate_cloud(f"{self.base_url}/workspaces/{self.org_or_project}/members")
            for m in members:
                user = m.get("user", {})
                rows.append({
                    "platform": self.platform,
                    "org": self.org_or_project,
                    "record_type": "workspace_member",
                    "identifier": user.get("nickname") or user.get("display_name", ""),
                    "scope": user.get("type", ""),
                    "updated_at": "",
                    "owner": "",
                })
        else:
            users = self._paginate_server(f"{self.base_url}/projects/{self.org_or_project}/permissions/users")
            for u in users:
                user = u.get("user", {})
                rows.append({
                    "platform": self.platform,
                    "org": self.org_or_project,
                    "record_type": "project_user",
                    "identifier": user.get("name", ""),
                    "scope": u.get("permission", ""),
                    "updated_at": "",
                    "owner": "",
                })
        return rows

    def list_pull_requests(
        self, repo: Dict[str, Any], since: Optional[str] = None, until: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if self.deployment_type == "cloud":
            prs = self._paginate_cloud(f"{self.base_url}/repositories/{repo['full_name']}/pullrequests?state=ALL")
            for pr in prs:
                created = pr.get("created_on", "")
                if (since and created < since) or (until and created > until):
                    continue
                rows.append({
                    "platform": self.platform,
                    "org": self.org_or_project,
                    "repo": repo["name"],
                    "pr_id": str(pr.get("id")),
                    "state": pr.get("state", ""),
                    "author": (pr.get("author") or {}).get("display_name", ""),
                    "created_at": created,
                    "merged_at": pr.get("updated_on", "") if pr.get("state") == "MERGED" else "",
                    "closed_at": pr.get("updated_on", "") if pr.get("state") in ("MERGED", "DECLINED") else "",
                })
        else:
            prs = self._paginate_server(
                f"{self.base_url}/projects/{self.org_or_project}/repos/{repo['name']}/pull-requests",
                {"state": "ALL"},
            )
            for pr in prs:
                created_ms = pr.get("createdDate")
                created = (
                    datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
                    if created_ms
                    else ""
                )
                if (since and created < since) or (until and created > until):
                    continue
                rows.append({
                    "platform": self.platform,
                    "org": self.org_or_project,
                    "repo": repo["name"],
                    "pr_id": str(pr.get("id")),
                    "state": pr.get("state", ""),
                    "author": ((pr.get("author") or {}).get("user") or {}).get("name", ""),
                    "created_at": created,
                    "merged_at": "",
                    "closed_at": "",
                })
        return rows