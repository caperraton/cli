from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class VCSClient(ABC):
    def __init__(
        self,
        platform: str,
        deployment_type: str,
        base_url: str,
        token: str,
        org_or_project: str,
        verify_ssl: bool = True,
    ):
        self.platform = platform
        self.deployment_type = deployment_type
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.org_or_project = org_or_project
        self.verify_ssl = verify_ssl

    @abstractmethod
    def list_repos(self) -> List[Dict[str, Any]]:
        """Return normalized repo dicts: name, full_name, archived, pushed_at, size_kb, html_url."""

    @abstractmethod
    def check_owner_and_ci(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'has_codeowners': bool, 'has_ci': bool, 'ci_type': str}."""

    @abstractmethod
    def list_apps_and_service_accounts(self) -> List[Dict[str, Any]]:
        """Return normalized app/service-account inventory rows."""

    @abstractmethod
    def list_pull_requests(
        self,
        repo: Dict[str, Any],
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return normalized PR metrics rows for observability/backfill."""