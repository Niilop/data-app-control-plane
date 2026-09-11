"""Admin-owned environment policy and atomic, versioned application bindings."""

from uuid import UUID

from core.config import Settings, get_settings
from models.database import User
from models.environment_schemas import (
    BindingCreate,
    BindingResponse,
    BindingUpdate,
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentUpdate,
)
from models.platform import Application, Environment, EnvironmentBinding, utcnow
from services import audit_service
from services.application_service import transaction
from services.policy_service import (
    PolicyError,
    get_application,
    require_active,
    require_admin,
    visible_applications,
)
from sqlalchemy import Select, select
from sqlalchemy.orm import Session


def require_local_simulation(settings: Settings) -> None:
    # A service must not rely solely on the API having validated startup settings.
    if (
        settings.runtime_profile != "local"
        or settings.deployment_executor != "simulated"
    ):
        raise PolicyError(
            422,
            "unsupported_execution",
            "Only explicitly configured local simulation is supported",
        )


def visible_environments(actor: User) -> Select:
    require_active(actor)
    query = select(Environment)
    if not actor.is_platform_admin:
        applications = visible_applications(actor).with_only_columns(Application.id)
        query = query.where(
            Environment.id.in_(
                select(EnvironmentBinding.environment_id).where(
                    EnvironmentBinding.application_id.in_(applications)
                )
            )
        )
    return query


def get_environment(db: Session, actor: User, environment_id: UUID) -> Environment:
    environment = db.scalar(
        visible_environments(actor).where(Environment.id == environment_id)
    )
    if environment is None:
        raise PolicyError(404, "not_found", "Environment not found")
    return environment


def lock_environment(
    db: Session, environment_id: UUID, *, missing_status: int = 422
) -> Environment:
    # Serialize policy edits with binding creation/update; always lock this row first.
    environment = db.scalar(
        select(Environment)
        .where(Environment.id == environment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if environment is None:
        raise PolicyError(
            missing_status,
            "not_found" if missing_status == 404 else "invalid_environment",
            "Environment does not exist",
        )
    return environment


def require_target(environment: Environment, target: str) -> None:
    if not environment.enabled:
        raise PolicyError(409, "environment_disabled", "Environment is disabled")
    if (
        environment.allowed_executor != "simulated"
        or not environment.workspace_ref.startswith("simulated://")
    ):
        raise PolicyError(
            422, "unsupported_execution", "Environment does not match local simulation"
        )
    if target not in environment.allowed_bundle_targets:
        raise PolicyError(
            422,
            "unapproved_target",
            "Bundle target is not approved for this environment",
        )


def environment_details(environment: Environment) -> dict:
    return EnvironmentResponse.model_validate(environment).model_dump(mode="json")


def create_environment(
    db: Session, actor: User, data: EnvironmentCreate, request_id: str
) -> Environment:
    with transaction(db):
        require_admin(actor)
        require_local_simulation(get_settings())
        environment = Environment(**data.model_dump())
        db.add(environment)
        db.flush()
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "environment.created",
            "environment",
            environment.id,
            environment_details(environment),
        )
    return environment


def update_environment(
    db: Session,
    actor: User,
    environment_id: UUID,
    data: EnvironmentUpdate,
    request_id: str,
) -> Environment:
    with transaction(db):
        require_admin(actor)
        require_local_simulation(get_settings())
        environment = lock_environment(db, environment_id, missing_status=404)
        if environment.version != data.expected_version:
            raise PolicyError(
                409, "stale_version", "Environment changed; reload before saving"
            )
        before = environment_details(environment)
        for field, value in data.model_dump(
            exclude_unset=True, exclude={"expected_version"}
        ).items():
            setattr(environment, field, value)
        environment.version += 1
        environment.updated_at = utcnow()
        after = environment_details(environment)
        # Any environment change invalidates every affected binding snapshot.
        # Binding writers hold the environment lock too, so none can miss the bump.
        for binding in db.scalars(
            select(EnvironmentBinding)
            .where(EnvironmentBinding.environment_id == environment_id)
            .order_by(EnvironmentBinding.id)
        ):
            binding.version += 1
            binding.updated_at = utcnow()
            audit_service.record_audit(
                db,
                actor,
                request_id,
                "binding.environment_changed",
                "environment_binding",
                binding.id,
                {
                    "environment_before": before,
                    "environment_after": after,
                    "version": binding.version,
                },
                binding.application_id,
            )
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "environment.updated",
            "environment",
            environment.id,
            {"before": before, "after": after},
        )
    return environment


def binding_response(db: Session, binding: EnvironmentBinding) -> BindingResponse:
    environment = db.get(Environment, binding.environment_id)
    application = db.get(Application, binding.application_id)
    assert environment is not None and application is not None
    return BindingResponse(
        id=binding.id,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
        version=binding.version,
        application_id=binding.application_id,
        environment_id=binding.environment_id,
        bundle_target=binding.bundle_target,
        config=binding.config,
        environment=EnvironmentResponse.model_validate(environment),
        usable=environment.enabled
        and application.lifecycle != "archived"
        and binding.bundle_target in environment.allowed_bundle_targets,
    )


def create_binding(
    db: Session, actor: User, application_id: UUID, data: BindingCreate, request_id: str
) -> EnvironmentBinding:
    with transaction(db):
        require_admin(actor)
        require_local_simulation(get_settings())
        application = get_application(db, actor, application_id)
        if application.lifecycle == "archived":
            raise PolicyError(
                409, "application_archived", "Archived applications cannot be bound"
            )
        environment = lock_environment(db, data.environment_id)
        require_target(environment, data.bundle_target)
        binding = EnvironmentBinding(application_id=application_id, **data.model_dump())
        db.add(binding)
        db.flush()
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "binding.created",
            "environment_binding",
            binding.id,
            binding_response(db, binding).model_dump(mode="json"),
            application_id,
        )
    return binding


def update_binding(
    db: Session,
    actor: User,
    application_id: UUID,
    binding_id: UUID,
    data: BindingUpdate,
    request_id: str,
) -> EnvironmentBinding:
    with transaction(db):
        require_admin(actor)
        require_local_simulation(get_settings())
        application = get_application(db, actor, application_id)
        if application.lifecycle == "archived":
            raise PolicyError(
                409,
                "application_archived",
                "Archived application bindings cannot be changed",
            )
        query = select(EnvironmentBinding).where(
            EnvironmentBinding.id == binding_id,
            EnvironmentBinding.application_id == application_id,
        )
        binding = db.scalar(query)
        if binding is None:
            raise PolicyError(404, "not_found", "Binding not found")
        environment = lock_environment(db, binding.environment_id)
        # Reload after acquiring the environment lock to observe any competing update.
        binding = db.scalar(query.execution_options(populate_existing=True))
        assert binding is not None
        if binding.version != data.expected_version:
            raise PolicyError(
                409, "stale_version", "Binding changed; reload before saving"
            )
        require_target(environment, data.bundle_target or binding.bundle_target)
        before = binding_response(db, binding).model_dump(mode="json")
        if data.bundle_target is not None:
            binding.bundle_target = data.bundle_target
        if data.config is not None:
            binding.config = data.config.model_dump()
        binding.version += 1
        binding.updated_at = utcnow()
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "binding.updated",
            "environment_binding",
            binding.id,
            {
                "before": before,
                "after": binding_response(db, binding).model_dump(mode="json"),
            },
            application_id,
        )
    return binding
