"""Offline tests for template generation, artifacts, revisions and validation."""

import io
import json
import zipfile
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

TEMPLATE = {"template_name": "python-batch", "template_version": "1.0.0"}
VALUES = {
    "application_slug": "synthetic-sales",
    "package_name": "synthetic_sales",
    "package_dist_name": "synthetic-sales",
    "bundle_target": "sandbox",
    "synthetic_output_path": "output/synthetic.csv",
    "synthetic_row_count": "100",
    "max_runtime_seconds": "300",
    "template_name": "python-batch",
    "template_version": "1.0.0",
}


@pytest.fixture
def delivery(registry: tuple) -> tuple:
    """An application with a usable binding and a developer plus operator actor."""
    client, headers, engine, team_id = registry
    application = client.post(
        "/api/v1/applications",
        headers=headers[2],
        json={
            "slug": "synthetic-sales",
            "name": "Synthetic sales",
            "description": "Sandbox batch application",
            "owning_team_id": team_id,
            "owner_user_id": 2,
            "data_owner_user_id": 2,
            "repository_url": "https://github.com/example/synthetic-sales",
            "bundle_root": ".",
        },
    )
    assert application.status_code == 201, application.text
    app_id = application.json()["id"]
    environment = client.post(
        "/api/v1/environments",
        headers=headers[1],
        json={
            "name": "Local sandbox",
            "workspace_ref": "simulated://local-sandbox",
            "allowed_executor": "simulated",
            "allowed_bundle_targets": ["sandbox"],
        },
    )
    assert environment.status_code == 201, environment.text
    binding = client.post(
        f"/api/v1/applications/{app_id}/bindings",
        headers=headers[1],
        json={"environment_id": environment.json()["id"], "bundle_target": "sandbox"},
    )
    assert binding.status_code == 201, binding.text
    for user_id, role in ((3, "viewer"), (2, "operator")):
        assert (
            client.post(
                f"/api/v1/applications/{app_id}/roles",
                headers=headers[2],
                json={"user_id": user_id, "role": role},
            ).status_code
            == 201
        )
    return client, headers, engine, app_id, binding.json()["id"]


def work(engine: object) -> None:
    """Run queued operations with the real worker until the queue drains."""
    from worker import run_one

    sessions = sessionmaker(engine)  # type: ignore[arg-type]
    for _ in range(10):
        if not run_one(sessions, str(uuid4())):
            return
    raise AssertionError("Queue did not drain")


def generate(delivery: tuple, **overrides: object) -> dict:
    client, headers, engine, app_id, binding_id = delivery
    body = {
        **TEMPLATE,
        "binding_id": binding_id,
        "package_name": "synthetic_sales",
        **overrides,
    }
    response = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": str(uuid4())},
        json=body,
    )
    assert response.status_code == 202, response.text
    work(engine)
    return response.json()


def artifacts(delivery: tuple, actor: int = 2) -> list[dict]:
    client, headers, _, app_id, _ = delivery
    response = client.get(
        f"/api/v1/applications/{app_id}/artifacts", headers=headers[actor]
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- Template catalogue and deterministic archives ---------------------------


def test_template_catalogue_lists_the_reviewed_version(registry: tuple) -> None:
    client, headers, _, _ = registry
    response = client.get("/api/v1/templates", headers=headers[2])
    assert response.status_code == 200, response.text
    template = response.json()[0]
    assert template["name"] == "python-batch" and template["active"]
    assert len(template["content_digest"]) == 64
    assert {"pyproject.toml", "uv.lock", ".github/workflows/ci.yml"} <= set(
        template["produces"]
    )
    assert [item["name"] for item in template["supplied_parameters"]] == [
        "package_name",
        "synthetic_output_path",
    ]


def test_templates_require_authentication(registry: tuple) -> None:
    client, _, _, _ = registry
    assert client.get("/api/v1/templates").status_code == 401


def test_same_template_and_inputs_yield_the_same_digest() -> None:
    from services.template_service import build_archive, get_template

    template = get_template("python-batch", "1.0.0")
    first = build_archive(template, VALUES)
    second = build_archive(template, dict(VALUES))
    assert first == second
    changed = build_archive(template, {**VALUES, "package_name": "other_package"})
    assert changed != first


def test_archive_entries_are_normalized_and_ordered() -> None:
    from services.template_service import build_archive, get_template

    content = build_archive(get_template("python-batch", "1.0.0"), VALUES)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = archive.infolist()
    assert [info.filename for info in infos] == sorted(info.filename for info in infos)
    for info in infos:
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.external_attr == 0o100644 << 16
        assert info.create_system == 3


def test_generation_reads_no_network() -> None:
    """The suite's autouse guard rejects sockets; generation must not open one."""
    from services.template_service import build_archive, get_template, load_catalogue

    load_catalogue.cache_clear()
    assert build_archive(get_template("python-batch", "1.0.0"), VALUES)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../escape.txt",
        "nested/../../escape.txt",
        "back\\slash.txt",
        "trailing/",
        "",
        "C:/windows",
        "bad\x00name",
    ],
)
def test_unsafe_archive_paths_are_rejected(path: str) -> None:
    from services.template_service import GenerationError, safe_archive_path

    with pytest.raises(GenerationError) as error:
        safe_archive_path(path)
    assert error.value.code == "unsafe_archive_entry"


def test_unknown_placeholder_is_a_template_defect() -> None:
    from services.template_service import GenerationError, render

    with pytest.raises(GenerationError) as error:
        render("@@unknown_thing@@", VALUES)
    assert error.value.code == "unknown_template_parameter"


def test_unknown_template_version_is_rejected() -> None:
    from services.template_service import GenerationError, get_template

    with pytest.raises(GenerationError) as error:
        get_template("python-batch", "9.9.9")
    assert error.value.code == "unknown_template"


def test_stored_archive_rejects_a_traversing_entry() -> None:
    from services.template_service import GenerationError, read_archive

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.txt", b"x")
    with pytest.raises(GenerationError) as error:
        read_archive(buffer.getvalue())
    assert error.value.code == "unsafe_archive_entry"


def test_stored_archive_rejects_a_symlink_entry() -> None:
    from services.template_service import GenerationError, read_archive

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = 0o120777 << 16  # S_IFLNK
        archive.writestr(info, b"/etc/passwd")
    with pytest.raises(GenerationError) as error:
        read_archive(buffer.getvalue())
    assert error.value.code == "unsafe_archive_entry"


# --- Parameter validation ----------------------------------------------------


@pytest.mark.parametrize(
    "package",
    ["Upper", "1leading", "has-hyphen", "class", "tests", "__dunder__", "x" * 41, ""],
)
def test_invalid_package_names_are_rejected(delivery: tuple, package: str) -> None:
    client, headers, _, app_id, binding_id = delivery
    response = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": str(uuid4())},
        json={**TEMPLATE, "binding_id": binding_id, "package_name": package},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/out.csv",
        "../escape.csv",
        "out.txt",
        "a/b/c/d/e/out.csv",
        "Out.csv",
        "out.csv;rm -rf /",
    ],
)
def test_invalid_output_paths_are_rejected(delivery: tuple, path: str) -> None:
    client, headers, _, app_id, binding_id = delivery
    response = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": str(uuid4())},
        json={
            **TEMPLATE,
            "binding_id": binding_id,
            "package_name": "synthetic_sales",
            "synthetic_output_path": path,
        },
    )
    assert response.status_code == 422, response.text


def test_secret_like_parameters_are_rejected(delivery: tuple) -> None:
    """The payload is closed: no credential, command or URL field exists."""
    client, headers, _, app_id, binding_id = delivery
    for extra in (
        {"databricks_token": "dapi-secret"},
        {"password": "hunter2"},
        {"command": "curl http://example.test"},
        {"workspace_url": "https://example.cloud.databricks.com"},
        {"bundle_target": "production"},
        {"application_slug": "other-application"},
    ):
        response = client.post(
            f"/api/v1/applications/{app_id}/generations",
            headers={**headers[2], "Idempotency-Key": str(uuid4())},
            json={
                **TEMPLATE,
                "binding_id": binding_id,
                "package_name": "synthetic_sales",
                **extra,
            },
        )
        assert response.status_code == 422, (extra, response.text)


# --- Generation authorization and operations ---------------------------------


def test_generation_requires_a_developer_role(delivery: tuple) -> None:
    client, headers, _, app_id, binding_id = delivery
    response = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[3], "Idempotency-Key": str(uuid4())},
        json={**TEMPLATE, "binding_id": binding_id, "package_name": "synthetic_sales"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_generation_hides_applications_the_actor_cannot_read(delivery: tuple) -> None:
    client, headers, _, app_id, binding_id = delivery
    response = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[4], "Idempotency-Key": str(uuid4())},
        json={**TEMPLATE, "binding_id": binding_id, "package_name": "synthetic_sales"},
    )
    assert response.status_code == 404


def test_generation_requires_an_idempotency_key(delivery: tuple) -> None:
    client, headers, _, app_id, binding_id = delivery
    response = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers=headers[2],
        json={**TEMPLATE, "binding_id": binding_id, "package_name": "synthetic_sales"},
    )
    assert response.status_code == 422


def test_repeated_key_returns_the_original_operation(delivery: tuple) -> None:
    client, headers, engine, app_id, binding_id = delivery
    key = str(uuid4())
    body = {**TEMPLATE, "binding_id": binding_id, "package_name": "synthetic_sales"}
    first = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": key},
        json=body,
    )
    second = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["operation_id"] == second.json()["operation_id"]
    conflict = client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": key},
        json={**body, "package_name": "different_package"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_generation_is_local_work_not_simulated(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    accepted = generate(delivery)
    assert accepted["execution_mode"] == "local"
    operation = client.get(
        f"/api/v1/operations/{accepted['operation_id']}", headers=headers[2]
    ).json()
    assert operation["kind"] == "bundle_generation"
    assert operation["execution_mode"] == "local"
    assert operation["status"] == "succeeded"


def test_generation_takes_no_binding_reservation(delivery: tuple) -> None:
    """A queued generation must not block execution work on the same binding."""
    from models.operations import OperationReservation

    client, headers, engine, app_id, binding_id = delivery
    client.post(
        f"/api/v1/applications/{app_id}/generations",
        headers={**headers[2], "Idempotency-Key": str(uuid4())},
        json={**TEMPLATE, "binding_id": binding_id, "package_name": "synthetic_sales"},
    )
    with Session(engine) as db:  # type: ignore[arg-type]
        assert db.get(OperationReservation, UUID(binding_id)) is None


def test_generation_produces_a_downloadable_artifact(delivery: tuple) -> None:
    client, headers, _, app_id, _ = delivery
    generate(delivery)
    items = artifacts(delivery)
    assert len(items) == 1
    artifact = items[0]
    assert artifact["kind"] == "generated_bundle"
    assert artifact["media_type"] == "application/zip"
    assert artifact["provenance"]["template_name"] == "python-batch"
    assert "password" not in json.dumps(artifact["provenance"]).lower()
    download = client.get(f"/api/v1/artifacts/{artifact['digest']}", headers=headers[2])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert download.headers["x-artifact-digest"] == artifact["digest"]
    import hashlib

    assert hashlib.sha256(download.content).hexdigest() == artifact["digest"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert "databricks.yml" in archive.namelist()
        assert b"sandbox" in archive.read("databricks.yml")


def test_identical_requests_produce_one_stored_artifact(delivery: tuple) -> None:
    first = generate(delivery)
    second = generate(delivery)
    assert first["operation_id"] != second["operation_id"]
    items = artifacts(delivery)
    assert len(items) == 1


def test_download_requires_application_access(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    generate(delivery)
    digest = artifacts(delivery)[0]["digest"]
    assert (
        client.get(f"/api/v1/artifacts/{digest}", headers=headers[3]).status_code == 200
    )
    denied = client.get(f"/api/v1/artifacts/{digest}", headers=headers[4])
    assert denied.status_code == 404
    assert client.get(f"/api/v1/artifacts/{digest}").status_code == 401


def test_download_rejects_a_malformed_digest(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    for digest in ("../../etc/passwd", "z" * 64, "abc"):
        response = client.get(f"/api/v1/artifacts/{digest}", headers=headers[2])
        assert response.status_code in (404, 422), digest


def test_download_rejects_content_that_fails_verification(delivery: tuple) -> None:
    from integrations import artifact_store

    client, headers, _, _, _ = delivery
    generate(delivery)
    digest = artifacts(delivery)[0]["digest"]
    path = artifact_store.artifact_root() / artifact_store.storage_key(digest)
    path.write_bytes(b"tampered content")
    response = client.get(f"/api/v1/artifacts/{digest}", headers=headers[2])
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "artifact_digest_mismatch"


def test_artifacts_survive_a_new_api_process(delivery: tuple) -> None:
    """Content lives in the configured mount, not in one process's memory."""
    from integrations import artifact_store

    generate(delivery)
    digest = artifacts(delivery)[0]["digest"]
    assert artifact_store.exists(digest)
    from core.config import get_settings

    get_settings.cache_clear()
    assert artifact_store.get(digest)


# --- Revisions ---------------------------------------------------------------


def capture(delivery: tuple, actor: int = 2, **overrides: object) -> dict:
    client, headers, _, app_id, binding_id = delivery
    body = {
        "artifact_digest": artifacts(delivery)[0]["digest"],
        "binding_id": binding_id,
        **overrides,
    }
    return client.post(
        f"/api/v1/applications/{app_id}/revisions", headers=headers[actor], json=body
    )


def test_revision_captures_an_immutable_snapshot(delivery: tuple) -> None:
    client, headers, _, app_id, binding_id = delivery
    generate(delivery)
    response = capture(delivery)
    assert response.status_code == 201, response.text
    revision = response.json()
    assert revision["source_kind"] == "generated_artifact"
    assert revision["bundle_target"] == "sandbox"
    assert revision["binding_snapshot"]["environment"]["workspace_ref"].startswith(
        "simulated://"
    )
    assert revision["config_snapshot"]["synthetic_row_count"] == 100
    assert len(revision["scope_digest"]) == 64
    assert response.headers["location"] == f"/api/v1/revisions/{revision['id']}"


def test_revision_cannot_be_edited(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    path = f"/api/v1/revisions/{revision['id']}"
    for method in (client.patch, client.put, client.delete):
        assert method(path, headers=headers[2]).status_code == 405


def test_new_configuration_creates_a_new_revision(delivery: tuple) -> None:
    generate(delivery)
    first = capture(delivery).json()
    second = capture(
        delivery,
        config={
            "schema_version": 1,
            "synthetic_row_count": 250,
            "max_runtime_seconds": 300,
        },
    ).json()
    assert first["id"] != second["id"]
    assert first["scope_digest"] != second["scope_digest"]
    assert first["config_digest"] != second["config_digest"]
    assert second["config_snapshot"]["synthetic_row_count"] == 250


def test_revision_requires_a_developer_role(delivery: tuple) -> None:
    generate(delivery)
    assert capture(delivery, actor=3).status_code == 403
    assert capture(delivery, actor=4).status_code == 404


def test_revision_rejects_an_uncaptured_artifact(delivery: tuple) -> None:
    client, headers, _, app_id, binding_id = delivery
    response = client.post(
        f"/api/v1/applications/{app_id}/revisions",
        headers=headers[2],
        json={"artifact_digest": "a" * 64, "binding_id": binding_id},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_artifact"


def test_revision_rejects_a_stale_binding_version(delivery: tuple) -> None:
    generate(delivery)
    response = capture(delivery, expected_binding_version=99)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_binding"


def test_revision_rejects_a_disabled_environment(delivery: tuple) -> None:
    client, headers, _, app_id, _ = delivery
    generate(delivery)
    environment = client.get("/api/v1/environments", headers=headers[1]).json()[
        "items"
    ][0]
    assert (
        client.patch(
            f"/api/v1/environments/{environment['id']}",
            headers=headers[1],
            json={"expected_version": environment["version"], "enabled": False},
        ).status_code
        == 200
    )
    response = capture(delivery)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "environment_disabled"


def test_revision_rejects_secret_configuration(delivery: tuple) -> None:
    generate(delivery)
    response = capture(
        delivery,
        config={"schema_version": 1, "databricks_token": "dapi-secret"},
    )
    assert response.status_code == 422


# --- Offline validation ------------------------------------------------------


def validate(delivery: tuple, revision_id: str, actor: int = 2) -> dict:
    client, headers, engine, _, _ = delivery
    response = client.post(
        f"/api/v1/revisions/{revision_id}/validations",
        headers={**headers[actor], "Idempotency-Key": str(uuid4())},
        json={"scope": "offline"},
    )
    if response.status_code == 202:
        work(engine)
    return response


def test_offline_validation_passes_and_stores_a_report(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    accepted = validate(delivery, revision["id"])
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["execution_mode"] == "local"
    results = client.get(
        f"/api/v1/revisions/{revision['id']}/validations", headers=headers[2]
    ).json()["items"]
    assert len(results) == 1
    result = results[0]
    assert result["scope"] == "offline"
    assert result["result"] == "passed"
    assert result["validator"] == "control-plane-offline"
    assert result["check_summary"]["failed"] == []
    assert result["observed_at"]
    report = client.get(
        f"/api/v1/artifacts/{artifacts(delivery)[0]['digest']}", headers=headers[2]
    )
    assert report.status_code == 200


def test_validation_report_is_explicitly_offline(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    validate(delivery, revision["id"])
    reports = [
        item for item in artifacts(delivery) if item["kind"] == "validation_report"
    ]
    assert len(reports) == 1
    content = client.get(
        f"/api/v1/artifacts/{reports[0]['digest']}", headers=headers[2]
    ).json()
    assert content["scope"] == "offline"
    assert content["result"] == "passed"
    assert any("workspace" in line for line in content["limitations"])
    assert "workspace_validation" not in json.dumps(content)
    assert all(check["passed"] for check in content["checks"])


def test_validation_scope_cannot_be_workspace(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    for scope in ("workspace", "databricks", "production"):
        response = client.post(
            f"/api/v1/revisions/{revision['id']}/validations",
            headers={**headers[2], "Idempotency-Key": str(uuid4())},
            json={"scope": scope},
        )
        assert response.status_code == 422, scope


def test_validation_fails_when_stored_content_is_replaced(delivery: tuple) -> None:
    """A digest mismatch stops validation instead of reporting on other content."""
    from integrations import artifact_store

    client, headers, _, _, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    digest = revision["artifact_digest"]
    (artifact_store.artifact_root() / artifact_store.storage_key(digest)).write_bytes(
        b"replaced"
    )
    validate(delivery, revision["id"])
    operations = client.get(
        f"/api/v1/applications/{revision['application_id']}/operations",
        headers=headers[2],
    ).json()["items"]
    validation = next(
        item for item in operations if item["kind"] == "offline_validation"
    )
    assert validation["status"] == "failed"
    assert validation["diagnostic_code"] == "artifact_digest_mismatch"
    results = client.get(
        f"/api/v1/revisions/{revision['id']}/validations", headers=headers[2]
    ).json()["items"]
    assert results == []


def test_validation_reports_a_tampered_archive(delivery: tuple) -> None:
    """Content that still matches its digest but is unsafe fails the checks."""
    from integrations import artifact_store
    from models.delivery import Artifact
    from services.template_service import digest_bytes

    client, headers, engine, app_id, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("README.md", b"not a generated project")
    tampered = buffer.getvalue()
    new_digest = digest_bytes(tampered)
    artifact_store.put(tampered)
    with Session(engine) as db:  # type: ignore[arg-type]
        from models.delivery import DeploymentRevision

        row = db.get(DeploymentRevision, UUID(revision["id"]))
        artifact = db.get(Artifact, UUID(revision["artifact_id"]))
        assert row is not None and artifact is not None
        artifact.digest = new_digest
        row.artifact_digest = new_digest
        db.commit()
    validate(delivery, revision["id"])
    results = client.get(
        f"/api/v1/revisions/{revision['id']}/validations", headers=headers[2]
    ).json()["items"]
    assert results[0]["result"] == "failed"
    assert "required_files" in results[0]["check_summary"]["failed"]


def test_validation_requires_a_developer_role(delivery: tuple) -> None:
    generate(delivery)
    revision = capture(delivery).json()
    assert validate(delivery, revision["id"], actor=3).status_code == 403
    assert validate(delivery, revision["id"], actor=4).status_code == 404


def test_validation_records_policy_drift_as_a_note(delivery: tuple) -> None:
    client, headers, _, app_id, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    environment = client.get("/api/v1/environments", headers=headers[1]).json()[
        "items"
    ][0]
    assert (
        client.patch(
            f"/api/v1/environments/{environment['id']}",
            headers=headers[1],
            json={
                "expected_version": environment["version"],
                "allowed_bundle_targets": ["sandbox", "extra"],
            },
        ).status_code
        == 200
    )
    validate(delivery, revision["id"])
    reports = [
        item for item in artifacts(delivery) if item["kind"] == "validation_report"
    ]
    content = client.get(
        f"/api/v1/artifacts/{reports[0]['digest']}", headers=headers[2]
    ).json()
    assert content["notes"]
    assert "policy has changed" in content["notes"][0]


# --- Recovery and reads ------------------------------------------------------


def test_local_work_cannot_be_retried_through_the_queue(delivery: tuple) -> None:
    client, headers, _, _, _ = delivery
    accepted = generate(delivery)
    response = client.post(
        f"/api/v1/operations/{accepted['operation_id']}/retry",
        headers={**headers[2], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "unsupported_retry"


def test_revision_reads_follow_application_visibility(delivery: tuple) -> None:
    client, headers, _, app_id, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    assert (
        client.get(
            f"/api/v1/revisions/{revision['id']}", headers=headers[3]
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/revisions/{revision['id']}", headers=headers[4]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/applications/{app_id}/revisions", headers=headers[4]
        ).status_code
        == 404
    )


def test_delivery_audit_records_the_actor_and_scope(delivery: tuple) -> None:
    client, headers, _, app_id, _ = delivery
    generate(delivery)
    revision = capture(delivery).json()
    events = client.get(
        f"/api/v1/applications/{app_id}/audit-events?limit=100", headers=headers[2]
    ).json()["items"]
    captured = next(item for item in events if item["action"] == "revision.captured")
    assert captured["actor_user_id"] == 2
    assert captured["details"]["scope_digest"] == revision["scope_digest"]
    queued = next(
        item
        for item in events
        if item["action"] == "operation.queued"
        and item["details"]["kind"] == "bundle_generation"
    )
    assert queued["details"]["execution_mode"] == "local"


def test_template_content_change_is_refused(delivery: tuple) -> None:
    """A registered version is immutable; edited assets require a new version."""
    from models.delivery import TemplateVersion
    from services.delivery_service import sync_template
    from services.policy_service import PolicyError
    from services.template_service import get_template

    client, headers, engine, _, _ = delivery
    generate(delivery)
    template = get_template("python-batch", "1.0.0")
    with Session(engine) as db:  # type: ignore[arg-type]
        row = db.scalar(
            __import__("sqlalchemy").select(TemplateVersion)  # noqa: PLC0415
        )
        assert row is not None
        row.content_digest = "b" * 64
        db.commit()
        with pytest.raises(PolicyError) as error:
            sync_template(db, template)
    assert error.value.code == "template_digest_mismatch"
