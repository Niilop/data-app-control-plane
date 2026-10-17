"""Read-only GitHub REST adapter. Fixed origins, bounded reads, no redirects by default."""

import http.client
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit

from services.template_service import MAX_BYTES

API_VERSION = "2026-03-10"
SHA = re.compile(r"[a-f0-9]{40}")


class GitHubError(Exception):
    def __init__(
        self, code: str, *, transient: bool = False, retry_after: int = 0
    ) -> None:
        self.code = code
        self.transient = transient
        self.retry_after = retry_after
        super().__init__(code)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


def http_get(url: str, headers: dict[str, str]) -> Response:
    """No automatic redirects, proxies or user-supplied origins; stream within bounds."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "api.github.com",
        "codeload.github.com",
    }:
        raise GitHubError("github_unsafe_url")
    connection = http.client.HTTPSConnection(parsed.netloc, timeout=10)
    deadline = time.monotonic() + 30
    try:
        connection.request(
            "GET",
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            headers=headers,
        )
        response = connection.getresponse()
        chunks, size = [], 0
        while True:
            if time.monotonic() > deadline:
                raise GitHubError("github_timeout", transient=True)
            block = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not block:
                break
            chunks.append(block)
            size += len(block)
            if size > MAX_BYTES:
                raise GitHubError("github_response_too_large")
        return Response(
            response.status,
            {k.lower(): v for k, v in response.getheaders()},
            b"".join(chunks),
        )
    except (OSError, http.client.HTTPException):
        raise GitHubError("github_unavailable", transient=True) from None
    finally:
        connection.close()


def positive(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GitHubError("github_invalid_response")
    return value


class GitHub:
    def __init__(self, repository: str, token: str | None = None) -> None:
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", repository
        ):
            raise GitHubError("github_invalid_repository")
        self.repository = repository
        self.base = f"https://api.github.com/repos/{repository}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "data-app-control-plane",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def request(self, url: str, *, archive: bool = False) -> Response:
        response = http_get(
            url,
            self.headers if not archive else {"User-Agent": self.headers["User-Agent"]},
        )
        if response.status in {403, 429} and (
            response.status == 429
            or "retry-after" in response.headers
            or response.headers.get("x-ratelimit-remaining") == "0"
        ):
            try:
                wait = max(
                    60,
                    int(response.headers.get("retry-after", "0")),
                    int(response.headers.get("x-ratelimit-reset", "0"))
                    - int(time.time()),
                )
            except ValueError:
                wait = 60
            if wait > 86400:
                raise GitHubError("github_rate_limit_too_long")
            raise GitHubError("github_rate_limited", transient=True, retry_after=wait)
        if response.status == 401:
            raise GitHubError("github_authentication_failed")
        if response.status == 403:
            raise GitHubError("github_permission_denied")
        if response.status == 404:
            raise GitHubError("github_not_found")
        if response.status >= 500:
            raise GitHubError("github_unavailable", transient=True)
        if response.status not in {200, 302}:
            raise GitHubError("github_unexpected_status")
        return response

    def json(self, suffix: str) -> tuple[dict, Response]:
        response = self.request(self.base + suffix)
        if response.status != 200:
            raise GitHubError("github_redirect_rejected")
        try:
            value = json.loads(response.body)
            if not isinstance(value, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise GitHubError("github_invalid_response") from None
        return value, response

    def resolve(self, ref: str) -> tuple[int, str]:
        repository, _ = self.json("")
        if str(repository.get("full_name", "")).lower() != self.repository.lower():
            raise GitHubError("github_repository_changed")
        commit, _ = self.json(f"/commits/{quote(ref, safe='')}?per_page=1")
        sha = commit.get("sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise GitHubError("github_invalid_response")
        return positive(repository.get("id")), sha

    def verify_repository(self, repository_id: int) -> None:
        repository, _ = self.json("")
        if (
            repository.get("id") != repository_id
            or str(repository.get("full_name", "")).lower() != self.repository.lower()
        ):
            raise GitHubError("github_repository_changed")

    def archive(self, sha: str) -> bytes:
        if not SHA.fullmatch(sha):
            raise GitHubError("github_invalid_commit")
        response = self.request(self.base + "/zipball/" + sha)
        if response.status != 302:
            raise GitHubError("github_invalid_response")
        location = response.headers.get("location", "")
        parsed = urlsplit(location)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "codeload.github.com"
            or parsed.fragment
            or parsed.path
            not in {
                f"/{self.repository}/legacy.zip/{sha}",
                f"/{self.repository}/zip/{sha}",
            }
        ):
            raise GitHubError("github_redirect_rejected")
        # Signed private archive URLs may contain a short-lived query token.
        # Never forward the API authorization header or persist this URL.
        downloaded = self.request(location, archive=True)
        if downloaded.status != 200:
            raise GitHubError("github_redirect_rejected")
        return downloaded.body

    def runs(self, repository_id: int, sha: str) -> list[dict]:
        if not SHA.fullmatch(sha):
            raise GitHubError("github_invalid_commit")
        result, seen = [], set()
        expected_total: int | None = None
        for page in range(1, 11):
            data, response = self.json(
                "/actions/runs?"
                + urlencode({"head_sha": sha, "per_page": 100, "page": page})
            )
            rows = data.get("workflow_runs")
            total = data.get("total_count")
            if (
                not isinstance(rows, list)
                or len(rows) > 100
                or type(total) is not int
                or total < 0
            ):
                raise GitHubError("github_invalid_response")
            if total > 1000:
                raise GitHubError("github_pagination_limit")
            if expected_total is not None and total != expected_total:
                raise GitHubError("github_unstable_pagination", transient=True)
            expected_total = total
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or row.get("head_sha") != sha
                    or not isinstance(row.get("repository"), dict)
                    or row["repository"].get("id") != repository_id
                ):
                    raise GitHubError("github_invalid_response")
                run_id, attempt, workflow = (
                    positive(row.get("id")),
                    positive(row.get("run_attempt")),
                    positive(row.get("workflow_id")),
                )
                status, conclusion, event = (
                    row.get("status"),
                    row.get("conclusion"),
                    row.get("event"),
                )
                if (
                    not isinstance(status, str)
                    or (conclusion is not None and not isinstance(conclusion, str))
                    or status
                    not in {
                        "queued",
                        "in_progress",
                        "completed",
                        "waiting",
                        "requested",
                        "pending",
                    }
                    or conclusion
                    not in {
                        None,
                        "success",
                        "failure",
                        "neutral",
                        "cancelled",
                        "skipped",
                        "timed_out",
                        "action_required",
                        "stale",
                        "startup_failure",
                    }
                    or not isinstance(event, str)
                    or not re.fullmatch(r"[a-z_]{1,50}", event)
                ):
                    raise GitHubError("github_invalid_response")
                if (run_id, attempt) in seen:
                    raise GitHubError("github_unstable_pagination", transient=True)
                seen.add((run_id, attempt))
                result.append(
                    {
                        "run_id": run_id,
                        "run_attempt": attempt,
                        "workflow_id": workflow,
                        "status": status,
                        "conclusion": conclusion,
                        "event": event,
                        "url": f"https://github.com/{self.repository}/actions/runs/{run_id}/attempts/{attempt}",
                    }
                )
            more = 'rel="next"' in response.headers.get("link", "")
            if len(result) > total:
                raise GitHubError("github_unstable_pagination", transient=True)
            if not more and len(result) == total:
                return result
            if not rows:
                raise GitHubError("github_unstable_pagination", transient=True)
            # Construct page URLs ourselves; never follow provider-supplied Link URLs.
        raise GitHubError("github_pagination_limit")
