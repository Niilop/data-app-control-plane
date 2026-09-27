"""Pure fixed simulation; never imports or executes generated project code."""

from models.job_run_schemas import RunInput, RunResult


def execute(data: RunInput) -> RunResult:
    if data.scenario == "failure":
        return RunResult(
            lifecycle="terminated",
            outcome="failure",
            output=None,
            output_verified=False,
        )
    count = data.parameters.row_count
    return RunResult(
        lifecycle="terminated",
        outcome="success",
        output={"rows": count, "total": sum(range(count))},
        output_verified=True,
    )
