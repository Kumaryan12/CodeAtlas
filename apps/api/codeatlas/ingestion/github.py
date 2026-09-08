import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from codeatlas.core.errors import DomainError

# Accept repository roots only. Construct upstream URLs ourselves, never follow user URLs.
REPOSITORY_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9_.-]{1,100})/?"
)


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.full_name}"


def parse_github_url(value: str) -> GitHubRepository:
    match = REPOSITORY_URL.fullmatch(value.strip())
    if not match:
        raise DomainError(
            "invalid_url", "Enter a public repository URL: https://github.com/owner/repo"
        )
    owner, name = match.groups()
    name = name.removesuffix(".git")
    if not name or name in {".", ".."} or name.endswith("."):
        raise DomainError("invalid_url", "The repository name is invalid.")
    return GitHubRepository(owner, name)


@dataclass(frozen=True)
class Snapshot:
    full_name: str
    url: str
    branch: str
    commit_sha: str
    description: str | None


def check_response(response: httpx.Response) -> None:
    if response.status_code == 404:
        raise DomainError(
            "repository_unavailable", "Repository is private, missing, or empty.", 404
        )
    if response.status_code in {403, 429}:
        raise DomainError("github_rate_limit", "GitHub refused the request. Try again later.", 429)
    if response.status_code in {301, 302, 307, 308}:
        raise DomainError("repository_moved", "Repository moved. Use its current GitHub URL.")
    if response.status_code != 200:
        raise DomainError("github_unavailable", "GitHub could not provide this repository.", 502)


class GitHubClient:
    def __init__(self, client: httpx.Client, max_download_bytes: int, timeout_seconds: int):
        self.client = client
        self.max_download_bytes = max_download_bytes
        self.timeout_seconds = timeout_seconds

    def _download(self, url: str, target: Path, limit: int, deadline: float) -> None:
        size = 0
        with self.client.stream("GET", url) as response:
            check_response(response)
            # HTTP decompression is disabled so the actual transferred bytes are bounded.
            if response.headers.get("content-encoding", "identity") != "identity":
                raise DomainError("invalid_archive", "Unexpected GitHub transfer encoding.", 502)
            with target.open("wb") as output:
                for chunk in response.iter_raw():
                    size += len(chunk)
                    if size > limit:
                        raise DomainError(
                            "repository_too_large",
                            "Repository download exceeds the size limit.",
                            413,
                        )
                    if time.monotonic() > deadline:
                        raise DomainError(
                            "ingestion_timeout", "Repository download timed out.", 504
                        )
                    output.write(chunk)

    def download(self, repository: GitHubRepository, workspace: Path) -> Snapshot:
        import json

        deadline = time.monotonic() + self.timeout_seconds
        base = f"https://api.github.com/repos/{repository.full_name}"
        metadata_path = workspace / "metadata.json"
        commit_path = workspace / "commit.json"
        try:
            self._download(base, metadata_path, 1_000_000, deadline)
            data = json.loads(metadata_path.read_bytes())
            if data.get("private") is not False:
                raise DomainError(
                    "repository_unavailable", "Only public repositories are supported.", 404
                )
            branch = data["default_branch"]
            if not isinstance(branch, str) or not branch or len(branch) > 255:
                raise ValueError("Invalid branch")
            self._download(
                f"{base}/commits/{quote(branch, safe='')}", commit_path, 2_000_000, deadline
            )
            sha = json.loads(commit_path.read_bytes())["sha"]
            if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("Invalid commit")
            archive_url = f"https://codeload.github.com/{repository.full_name}/tar.gz/{sha}"
            self._download(
                archive_url, workspace / "repository.tar.gz", self.max_download_bytes, deadline
            )
            description = data.get("description")
            return Snapshot(
                repository.full_name,
                repository.url,
                branch,
                sha,
                description[:1000] if isinstance(description, str) else None,
            )
        except httpx.TimeoutException as exc:
            raise DomainError("ingestion_timeout", "GitHub did not respond in time.", 504) from exc
        except httpx.HTTPError as exc:
            raise DomainError(
                "github_unavailable", "Cannot connect to GitHub. Try again later.", 502
            ) from exc
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise DomainError(
                "github_response_invalid", "GitHub returned unexpected metadata.", 502
            ) from exc
