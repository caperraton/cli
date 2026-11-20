from datascrape.clients.base import VCSClient
from datascrape.clients.bitbucket import BitbucketClient
from datascrape.clients.github import GitHubClient


def build_client(
    target: str,
    deployment_type: str,
    url: str,
    token: str,
    org: str,
    verify_ssl: bool = True,
) -> VCSClient:
    t = target.lower()
    if t in ("github", "ghes"):
        dtype = "self_hosted" if t == "ghes" else deployment_type
        return GitHubClient(dtype, url, token, org, verify_ssl=verify_ssl)
    if t in ("bitbucket", "bitbucket_cloud", "bitbucket_server"):
        dtype = "self_hosted" if t == "bitbucket_server" else deployment_type
        return BitbucketClient(dtype, url, token, org, verify_ssl=verify_ssl)
    raise ValueError(f"Unsupported target: {target}. Use github, ghes, or bitbucket.")