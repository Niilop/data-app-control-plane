"""Fixed local simulation. References are observations, never provider resources."""

from uuid import UUID

from models.deployment_schemas import DeploymentInput


def execute(operation_id: UUID, data: DeploymentInput) -> tuple[str, list[dict]]:
    resources = [
        {
            "resource_key": "synthetic_job",
            "reference": f"simulated://deployment/{operation_id}/synthetic_job",
            "execution_mode": "simulated",
            "status": "created",
        }
    ]
    if data.scenario == "partial_failure":
        return "failed", resources
    resources[0]["status"] = "ready"
    return "succeeded", resources
