# Data application control plane: agent entry point

Documentation baseline: 2026-09-14. Implementation status on main: **T01–T04a merged;
T05 proposed separately in PR #11, pending review/merge.** The platform includes
owned applications, team/role administration, simulated environment bindings,
durable operation history and recovery. React + TypeScript + Vite now replaces
Streamlit; Docker serves the UI with nginx on localhost:8501. Existing accounts
and database history are preserved. Local simulation must remain explicit.
See [next-agent.md](next-agent.md) for verification and current limitations.
The next bounded task is **T05: Generate a bundle and capture a revision**; inspect
its existing PR before creating duplicate work. No generation, provider deployment
or organization identity exists on this documentation branch.

**Resume here:** [next-agent.md](next-agent.md). Verify prerequisite changes
on updated `main` before creating or continuing any task branch; the handoff
describes code state, not merge status, so re-confirm rather than trusting
this line indefinitely.

Build a self-service platform where a team requests onboarding of a Git repository
as a governed Databricks data application. The platform manages ownership, access
requests, revisions, approvals, deployment history, and run visibility. GitHub
Actions supplies CI/CD; Databricks executes data processing.

The first useful product runs locally for one developer. No Azure-hosted control
plane, paid subscription, or Databricks credentials are prerequisites for local
development. Real external execution is an explicitly enabled integration gate.

Terraform is planned as **T09a**, after GitHub workflow integration and before
T10's real Databricks deployment. It prepares a small sandbox foundation through
a separate administrator workflow; DAB remains the application deployment tool.
The API/worker will not run Terraform or manage its state. See
[development plan](development-plan.md#t09a--prepare-a-terraform-sandbox-foundation)
and ADR-018 in [decisions](decisions.md). No infrastructure is implemented or
activated by this planning update, and the local demo has no Terraform dependency.

## Reading path

1. Read the versioned root [AGENTS.md](../AGENTS.md).
2. Read [product-scope.md](product-scope.md) for agreed scope and provisional choices.
3. Select the assigned task in [development-plan.md](development-plan.md).
4. Read only its referenced contracts and the relevant entries in
   [repository-map.md](repository-map.md), then inspect those source files.
5. Implement and verify the task; update its handoff before stopping.

| Document | Use |
|---|---|
| [Product scope](product-scope.md) | Personas, boundaries, demo, deferred features |
| [Repository map](repository-map.md) | Current code, known gaps, planned code locations |
| [Architecture](architecture.md) | Processes, adapters, transactions, reliability |
| [Domain contracts](domain-contracts.md) | Entities, states, permissions, invariants |
| [API contracts](api-contracts.md) | Planned endpoints, payloads, errors, pagination |
| [GitHub and Databricks](integrations.md) | Generated repository, CI/CD, trust, cost boundaries |
| [Development plan](development-plan.md) | Ordered, bounded agent tasks and acceptance criteria |
| [Testing and operation](testing-and-operation.md) | Check strategy, target commands, recovery demonstrations |
| [Decisions](decisions.md) | Accepted direction, provisional choices, unresolved gates |
| [Original requirements](requirements-baseline.md) | Preserved preliminary input; historical context |

## Source of truth

User instructions take precedence. This documentation incorporates subsequent
clarifications: GitHub Actions first, local hosting, minimal cost, existing
repositories first, organizational ownership/access workflows. The original
requirements remain context, not a mandate to implement every enterprise feature.

The contracts describe intended behavior until their implementation tasks are
complete. Tests and implementation establish actual behavior; discrepancies must
be resolved and documented, not silently treated as completed work.

## Next agent assignment

Use this prompt (see [next-agent.md](next-agent.md) for the current, more
specific version):

> Read AGENTS.md, mdfiles/README.md, and mdfiles/next-agent.md. Inspect Git
> status, verify prerequisites on updated main, and inspect existing T05 PR #11
> before creating duplicate work. Continue T05 only if still outstanding, using
> the React frontend and existing durable
> worker contracts. Preserve accounts, data and unrelated work. Run the required
> checks, update the handoff/contracts/map, and open a draft PR. Do not merge,
> begin T06, publish repositories, or activate external providers.


The handoff separates implemented behavior from verification and merge status.
Infrastructure activation and later task completion are not implied by this plan.
