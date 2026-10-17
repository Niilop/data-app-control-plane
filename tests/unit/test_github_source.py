"""Offline provider, source integrity, queue recovery and authorization regressions."""

import io
import json
import stat
import zipfile
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from test_environments import bound

SHA = "a" * 40


def test_disabled_and_unauthorized_commands_leave_no_work(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.config import get_settings
    from models.operations import Operation

    app, binding, _, calls = setup(registry, monkeypatch)
    client, headers, engine, _ = registry
    path = f"/api/v1/applications/{app['id']}/source-captures"
    body = {"binding_id": binding["id"], "expected_binding_version": 1, "ref": "main"}
    for actor in (1, 3, 4, 5):
        assert client.post(
            path, headers={**headers[actor], "Idempotency-Key": "denied"}, json=body
        ).status_code == (404 if actor == 5 else 403)
    for ref in (
        "../secret",
        "main?token=secret",
        "https://evil.test",
        "main;curl",
        "main..old",
    ):
        assert (
            client.post(
                path,
                headers={**headers[2], "Idempotency-Key": "invalid"},
                json={**body, "ref": ref},
            ).status_code
            == 422
        )
    monkeypatch.setattr(get_settings(), "github_reads_enabled", False)
    assert submit(registry, app, binding).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(Operation)) is None
    assert not calls


def test_manual_retry_preserves_pin_after_terminal_failure(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from integrations.github import GitHub, GitHubError
    from models.platform import ApplicationRole
    from worker import run_one

    app, binding, _, _ = setup(registry, monkeypatch)
    client, headers, engine, _ = registry
    original = GitHub.archive

    def fail(*_):
        raise GitHubError("github_not_found")

    monkeypatch.setattr(GitHub, "archive", fail)
    accepted = submit(registry, app, binding).json()
    assert run_one(sessionmaker(engine), str(uuid4()))
    with Session(engine) as db:
        db.add(
            ApplicationRole(application_id=UUID(app["id"]), user_id=2, role="operator")
        )
        db.commit()
    retried = client.post(
        f"/api/v1/operations/{accepted['operation_id']}/retry",
        headers={**headers[2], "Idempotency-Key": "retry"},
    )
    assert retried.status_code == 202, retried.text
    monkeypatch.setattr(GitHub, "archive", original)
    monkeypatch.setattr(
        GitHub, "resolve", lambda *_: pytest.fail("Manual retry must keep the pin")
    )
    assert run_one(sessionmaker(engine), str(uuid4()))
    rows = client.get(
        f"/api/v1/applications/{app['id']}/source-captures", headers=headers[2]
    ).json()["items"]
    assert len(rows) == 2 and all(row["commit_sha"] == SHA for row in rows)
    assert sum(bool(row["artifact_digest"]) for row in rows) == 1


@pytest.mark.parametrize(
    "case", ["duplicate", "total_changes", "too_many", "empty_partial"]
)
def test_ci_rejects_incomplete_pagination(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from integrations import github

    calls = []

    def get(url, headers):
        calls.append(url)
        total = 1001 if case == "too_many" else 2
        if case == "total_changes" and len(calls) == 2:
            total = 1
        rows = [] if case == "empty_partial" else [run_row()]
        return github.Response(
            200, {}, json.dumps({"total_count": total, "workflow_runs": rows}).encode()
        )

    monkeypatch.setattr(github, "http_get", get)
    with pytest.raises(
        github.GitHubError,
        match="github_pagination_limit"
        if case == "too_many"
        else "github_unstable_pagination",
    ):
        github.GitHub("example/sales").runs(42, SHA)


def zip_source(files: dict[str, bytes], root: str = "bundles/sales") -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(f"example-sales-abcdef/{root}/{name}", data)
    return result.getvalue()


def setup(registry: tuple, monkeypatch: pytest.MonkeyPatch) -> tuple:
    from core.config import get_settings
    from integrations import github
    from models.delivery_schemas import TemplateParameters
    from services.template_service import render, unpack

    app, _, binding = bound(registry)
    settings = get_settings()
    monkeypatch.setattr(settings, "github_reads_enabled", True)
    monkeypatch.setattr(settings, "github_allowed_repositories", ["example/sales"])
    files = unpack(
        render(app["slug"], "sandbox", binding["config"], TemplateParameters())
    )
    calls = []

    def get(url: str, headers: dict) -> github.Response:
        calls.append((url, headers))
        if "/commits/" in url:
            return github.Response(200, {}, json.dumps({"sha": SHA}).encode())
        if "/zipball/" in url:
            return github.Response(
                302,
                {
                    "location": f"https://codeload.github.com/example/sales/legacy.zip/{SHA}?token=ephemeral"
                },
                b"",
            )
        if url.startswith("https://codeload.github.com/"):
            assert "Authorization" not in headers
            return github.Response(200, {}, zip_source(files))
        if "/actions/runs?" in url:
            return github.Response(
                200,
                {},
                json.dumps({"total_count": 1, "workflow_runs": [run_row()]}).encode(),
            )
        return github.Response(200, {}, b'{"id":42,"full_name":"example/sales"}')

    monkeypatch.setattr(github, "http_get", get)
    return app, binding, files, calls


def run_row(**changes: object) -> dict:
    return {
        "id": 12,
        "run_attempt": 1,
        "workflow_id": 4,
        "head_sha": SHA,
        "repository": {"id": 42},
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        **changes,
    }


def submit(registry: tuple, app: dict, binding: dict, key: str = "capture"):
    client, headers, _, _ = registry
    return client.post(
        f"/api/v1/applications/{app['id']}/source-captures",
        headers={**headers[2], "Idempotency-Key": key},
        json={
            "binding_id": binding["id"],
            "expected_binding_version": binding["version"],
            "ref": "main",
        },
    )


def test_capture_revision_validation_ci_and_private_download(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.source import CIRun, SourceCapture
    from worker import run_one

    app, binding, _, calls = setup(registry, monkeypatch)
    client, headers, engine, _ = registry
    monkeypatch.setenv("GITHUB_READ_TOKEN", "worker-only-secret")
    response = submit(registry, app, binding)
    assert response.status_code == 202, response.text
    assert response.json()["execution_mode"] == "github_read"
    assert not calls
    assert submit(registry, app, binding).json() == response.json()
    assert run_one(sessionmaker(engine), str(uuid4()))
    path = f"/api/v1/applications/{app['id']}"
    source = client.get(path + "/source-captures", headers=headers[2]).json()["items"][
        0
    ]
    assert source["commit_sha"] == SHA and source["artifact_digest"]
    assert client.get(path, headers=headers[2]).json()["repository_verified_at"]
    assert "worker-only-secret" not in json.dumps(source)
    downloaded = client.get(
        f"/api/v1/artifacts/{source['artifact_digest']}", headers=headers[2]
    )
    assert downloaded.status_code == 200
    for endpoint in (
        path + "/source-captures",
        path + "/ci-runs",
        path + "/source-policy",
        path + "/ci-onboarding",
        f"/api/v1/artifacts/{source['artifact_digest']}",
    ):
        assert client.get(endpoint, headers=headers[5]).status_code == 404
    created = client.post(
        path + "/revisions",
        headers=headers[2],
        json={
            "source_capture_id": source["id"],
            "binding_id": binding["id"],
            "expected_binding_version": 1,
        },
    )
    assert created.status_code == 201, created.text
    revision = created.json()
    assert revision["source_kind"] == "github" and revision["generation_id"] is None
    validations = f"/api/v1/revisions/{revision['id']}/validations"
    assert (
        client.post(
            validations,
            headers={**headers[2], "Idempotency-Key": "validate"},
            json={"scope": "offline"},
        ).status_code
        == 202
    )
    assert run_one(sessionmaker(engine), str(uuid4()))
    assert (
        client.get(validations, headers=headers[2]).json()["items"][0]["result"]
        == "passed"
    )
    refresh = f"/api/v1/source-captures/{source['id']}/ci-refresh"
    assert (
        client.post(
            refresh, json={}, headers={**headers[2], "Idempotency-Key": "ci"}
        ).status_code
        == 202
    )
    assert run_one(sessionmaker(engine), str(uuid4()))
    count = len(calls)
    observed = client.get(path + "/ci-runs", headers=headers[2]).json()["items"]
    assert len(observed) == 1 and observed[0]["commit_sha"] == SHA
    assert len(calls) == count  # Display does not poll providers.
    from models.platform import EnvironmentBinding

    with Session(engine) as db:
        db.get(EnvironmentBinding, UUID(binding["id"])).version += 1
        db.commit()
    repeated = client.post(
        refresh, json={}, headers={**headers[2], "Idempotency-Key": "ci"}
    )
    assert repeated.status_code == 202
    assert repeated.json()["operation_id"] == observed[0]["operation_id"]
    assert (
        client.post(
            refresh, json={}, headers={**headers[2], "Idempotency-Key": "new-ci"}
        ).status_code
        == 409
    )
    with Session(engine) as db:
        saved = db.get(SourceCapture, UUID(source["id"]))
        saved.commit_sha = "b" * 40
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        db.scalar(select(CIRun)).conclusion = "failure"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()


@pytest.mark.parametrize(
    "change",
    ["disabled", "allowlist", "role", "binding", "repository", "archived", "inactive"],
)
def test_worker_rechecks_policy(
    registry: tuple, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from core.config import get_settings
    from models.database import User
    from models.operations import Operation, OperationReservation
    from models.platform import Application, ApplicationRole, EnvironmentBinding
    from models.source import SourceCapture
    from worker import run_one

    app, binding, _, calls = setup(registry, monkeypatch)
    assert submit(registry, app, binding).status_code == 202
    with Session(registry[2]) as db:
        if change == "disabled":
            monkeypatch.setattr(get_settings(), "github_reads_enabled", False)
        elif change == "allowlist":
            monkeypatch.setattr(get_settings(), "github_allowed_repositories", [])
        elif change == "role":
            db.execute(
                delete(ApplicationRole).where(ApplicationRole.role == "developer")
            )
        elif change == "binding":
            db.get(EnvironmentBinding, UUID(binding["id"])).version += 1
        elif change == "repository":
            db.get(
                Application, UUID(app["id"])
            ).repository_url = "https://github.com/example/changed"
        elif change == "archived":
            db.get(Application, UUID(app["id"])).lifecycle = "archived"
        else:
            db.get(User, 2).is_active = False
        db.commit()
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    assert not calls
    with Session(registry[2]) as db:
        assert db.scalar(select(Operation)).status == "failed"
        assert db.scalar(select(SourceCapture)).artifact_digest is None
        assert db.scalar(select(OperationReservation)) is None


def test_pin_survives_rate_limit_and_moving_branch(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from integrations.github import GitHub, GitHubError
    from models.operations import Operation
    from models.platform import utcnow
    from models.source import SourceCapture
    from worker import run_one

    app, binding, _, calls = setup(registry, monkeypatch)
    original = GitHub.archive
    attempts = []

    def archive(self, commit):
        attempts.append(commit)
        if len(attempts) == 1:
            raise GitHubError("github_rate_limited", transient=True, retry_after=120)
        return original(self, commit)

    monkeypatch.setattr(GitHub, "archive", archive)
    assert submit(registry, app, binding).status_code == 202
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    with Session(registry[2]) as db:
        operation = db.scalar(select(Operation))
        assert (
            operation.status == "retry_wait"
            and operation.diagnostic_code == "github_rate_limited"
        )
        from services.queue_service import aware

        assert aware(operation.available_at) > utcnow() + timedelta(seconds=110)
        assert db.scalar(select(SourceCapture)).commit_sha == SHA
        operation.available_at = utcnow()
        db.commit()
    monkeypatch.setattr(
        GitHub,
        "resolve",
        lambda *_: pytest.fail("Must not resolve a moving branch twice"),
    )
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    assert attempts == [SHA, SHA]
    assert len([url for url, _ in calls if "/commits/" in url]) == 1


@pytest.mark.parametrize("change", ["cancel", "revoke", "repository"])
def test_result_rechecks_policy_after_network_read(
    registry: tuple, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from integrations.github import GitHub
    from models.operations import Operation
    from models.platform import Application, ApplicationRole
    from models.source import SourceCapture
    from worker import run_one

    app, binding, _, _ = setup(registry, monkeypatch)
    original = GitHub.archive

    def archive(self, commit):
        with Session(registry[2]) as db:
            if change == "cancel":
                db.scalar(select(Operation)).cancel_requested = True
            elif change == "revoke":
                db.execute(
                    delete(ApplicationRole).where(ApplicationRole.role == "developer")
                )
            else:
                db.get(Application, UUID(app["id"])).bundle_root = "changed"
            db.commit()
        return original(self, commit)

    monkeypatch.setattr(GitHub, "archive", archive)
    assert submit(registry, app, binding).status_code == 202
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    with Session(registry[2]) as db:
        assert db.scalar(select(Operation)).status == (
            "cancelled" if change == "cancel" else "failed"
        )
        assert db.scalar(select(SourceCapture)).artifact_digest is None
        assert db.get(Application, UUID(app["id"])).repository_verified_at is None


@pytest.mark.parametrize(
    "status,headers,code,transient",
    [
        (404, {}, "github_not_found", False),
        (401, {}, "github_authentication_failed", False),
        (403, {}, "github_permission_denied", False),
        (403, {"x-ratelimit-remaining": "0"}, "github_rate_limited", True),
        (429, {"retry-after": "90"}, "github_rate_limited", True),
        (503, {}, "github_unavailable", True),
    ],
)
def test_provider_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    headers: dict,
    code: str,
    transient: bool,
) -> None:
    from integrations import github

    monkeypatch.setattr(
        github,
        "http_get",
        lambda *_: github.Response(status, headers, b"secret-provider-response"),
    )
    with pytest.raises(github.GitHubError) as error:
        github.GitHub("example/sales", "private-token").resolve("main")
    assert str(error.value) == code and error.value.transient is transient


def test_ci_pagination_exact_commit_and_safe_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations import github

    calls = []

    def get(url, headers):
        calls.append(url)
        page = len(calls)
        return github.Response(
            200,
            {"link": '<https://evil.test/steal>; rel="next"'} if page == 1 else {},
            json.dumps(
                {
                    "total_count": 2,
                    "workflow_runs": [run_row(id=page, html_url="https://evil.test")],
                }
            ).encode(),
        )

    monkeypatch.setattr(github, "http_get", get)
    runs = github.GitHub("example/sales").runs(42, SHA)
    assert len(runs) == 2
    assert all(
        url.startswith("https://api.github.com/repos/example/sales/actions/runs?")
        and f"head_sha={SHA}" in url
        for url in calls
    )
    assert (
        runs[1]["url"] == "https://github.com/example/sales/actions/runs/2/attempts/1"
    )


@pytest.mark.parametrize(
    "row",
    [
        run_row(head_sha="b" * 40),
        run_row(repository={"id": 43}),
        run_row(status=[]),
        run_row(conclusion={}),
        run_row(id=True),
    ],
)
def test_ci_rejects_mismatched_or_malformed_runs(
    monkeypatch: pytest.MonkeyPatch, row: dict
) -> None:
    from integrations import github

    monkeypatch.setattr(
        github,
        "http_get",
        lambda *_: github.Response(
            200, {}, json.dumps({"total_count": 1, "workflow_runs": [row]}).encode()
        ),
    )
    with pytest.raises(github.GitHubError, match="github_invalid_response"):
        github.GitHub("example/sales").runs(42, SHA)


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.test/a",
        "http://codeload.github.com/example/sales/legacy.zip/" + SHA,
        "https://codeload.github.com/other/repo/legacy.zip/" + SHA,
        "https://api.github.com@evil.test/a",
    ],
)
def test_archive_redirect_allowlist(
    monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    from integrations import github

    monkeypatch.setattr(
        github, "http_get", lambda *_: github.Response(302, {"location": location}, b"")
    )
    with pytest.raises(github.GitHubError, match="github_redirect_rejected"):
        github.GitHub("example/sales").archive(SHA)


@pytest.mark.parametrize(
    "bad",
    [
        "traversal",
        "symlink",
        "duplicate",
        "encrypted",
        "oversized",
        "missing",
        "syntax",
        "secret",
        "second_root",
        "not_zip",
    ],
)
def test_malformed_archives(
    registry: tuple, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    from integrations.github import GitHubError
    from integrations.source_archive import capture_archive
    from services.template_service import MAX_BYTES

    _, binding, files, _ = setup(registry, monkeypatch)
    if bad == "missing":
        del files["manifest.json"]
    if bad == "syntax":
        files["tests/bad.py"] = b"def invalid:"
    if bad == "secret":
        files[".env"] = b"TOKEN=never-print"
    data = zip_source(files)
    if bad in {"traversal", "symlink", "duplicate", "second_root", "oversized"}:
        buffer = io.BytesIO(data)
        with zipfile.ZipFile(buffer, "a", zipfile.ZIP_DEFLATED) as archive:
            name = "example-sales-abcdef/bundles/sales/extra"
            if bad == "traversal":
                name += "/../bad"
            if bad == "duplicate":
                name = "example-sales-abcdef/bundles/sales/manifest.json"
            if bad == "second_root":
                name = "another/root"
            entry = zipfile.ZipInfo(name)
            if bad == "symlink":
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(
                entry, b"x" * (MAX_BYTES + 1) if bad == "oversized" else b"x"
            )
        data = buffer.getvalue()
    if bad == "encrypted":
        value = bytearray(data)
        offset = value.index(b"PK\x01\x02")
        value[offset + 8] |= 1
        data = bytes(value)
    if bad == "not_zip":
        data = b"no archive"
    with pytest.raises(GitHubError, match="github_invalid_bundle"):
        capture_archive(
            data,
            "bundles/sales",
            {"bundle_target": "sandbox", "config": binding["config"]},
        )
