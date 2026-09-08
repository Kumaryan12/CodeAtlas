import json

import httpx
import pytest

from codeatlas.core.errors import DomainError
from codeatlas.ingestion.github import GitHubClient, parse_github_url


@pytest.mark.parametrize(
    "url", ["https://github.com/owner/repo", " https://github.com/owner/repo.git/ "]
)
def test_normalizes_repository_url(url):
    assert parse_github_url(url).url == "https://github.com/owner/repo"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://github.com.evil.test/a/b",
        "https://user@github.com/a/b",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b?x=y",
        "https://github.com/a/b#x",
        "https://127.0.0.1/a/b",
        "file:///etc/passwd",
        "https://github.com/a/..",
        "https://github.com/a/%2e%2e",
        "https://github.com:443/a/b",
        "https://github.com/a/.git",
    ],
)
def test_rejects_non_repository_urls(url):
    with pytest.raises(DomainError):
        parse_github_url(url)


def response(data, status=200):
    raw = json.dumps(data).encode() if isinstance(data, dict) else data
    return httpx.Response(status, stream=httpx.ByteStream(raw))


def test_download_uses_fixed_hosts_and_pinned_commit(tmp_path):
    urls = []
    sha = "a" * 40

    def handler(request):
        urls.append(str(request.url))
        if len(urls) == 1:
            return response(
                {"private": False, "default_branch": "release/v1", "description": "demo"}
            )
        if len(urls) == 2:
            return response({"sha": sha})
        return response(b"archive")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        snapshot = GitHubClient(client, 1000, 10).download(
            parse_github_url("https://github.com/a/b"), tmp_path
        )
    assert urls == [
        "https://api.github.com/repos/a/b",
        "https://api.github.com/repos/a/b/commits/release%2Fv1",
        f"https://codeload.github.com/a/b/tar.gz/{sha}",
    ]
    assert snapshot.commit_sha == sha
    assert (tmp_path / "repository.tar.gz").read_bytes() == b"archive"


@pytest.mark.parametrize(
    "status,code",
    [
        (404, "repository_unavailable"),
        (403, "github_rate_limit"),
        (429, "github_rate_limit"),
        (302, "repository_moved"),
        (500, "github_unavailable"),
    ],
)
def test_upstream_errors_are_structured(tmp_path, status, code):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: response(b"secret", status))
    ) as client:
        with pytest.raises(DomainError) as error:
            GitHubClient(client, 100, 10).download(
                parse_github_url("https://github.com/a/b"), tmp_path
            )
    assert error.value.code == code
    assert "secret" not in error.value.message


def test_streaming_limit(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: response(b"x" * 50))) as client:
        with pytest.raises(DomainError, match="size limit"):
            GitHubClient(client, 10, 10)._download(
                "https://api.github.com/a", tmp_path / "data", 10, float("inf")
            )


def test_private_metadata_rejected(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: response({"private": True}))
    ) as client:
        with pytest.raises(DomainError, match="Only public"):
            GitHubClient(client, 100, 10).download(
                parse_github_url("https://github.com/a/b"), tmp_path
            )
