# Data application control plane: agent entry point

Documentation baseline: 2026-09-12. Implementation status: **T01–T04a merged;
T05 bundle generation implemented, pending review/merge.** The platform includes
owned applications, team/role administration, simulated environment bindings,
durable operation history and recovery, and now deterministic template generation,
digest-verified local artifacts, immutable revisions and explicitly offline
validation. React + TypeScript + Vite replaces Streamlit; Docker serves the UI
with nginx on localhost:8501. Existing accounts and database history are preserved.
Local simulation must remain explicit, and offline validation is never workspace
validation. See [next-agent.md](next-agent.md) for verification and limitations.
The next bounded task after T05 merges is **T06: Approve and simulate one
deployment**. No approval, provider deployment, repository publication or
organization identity exists yet.

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
> status and verify T05 is merged into updated main. Create the next task branch
> if needed and implement T06 only, binding approval to the exact recorded scope
> digest and rechecking it before simulated deployment. Preserve accounts, data
> and unrelated work. Run the required checks, update the handoff/contracts/map,
> and open a draft PR. Do not merge, begin T07, publish repositories, or activate
> external providers.


The handoff separates implemented behavior from verification and merge status.
Infrastructure activation and later task completion are not implied by this plan.
