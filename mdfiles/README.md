# Data application control plane: agent entry point

Documentation baseline: 2026-09-11. Implementation status: **T01/T02 merged;
T03 environment bindings implemented, pending PR review/merge.** The platform
includes an owned application registry and admin-managed simulated environments,
versioned bindings and audit. Docker builds/live startup remain unverified.
Existing local configuration now requires `DEPLOYMENT_EXECUTOR=simulated`.
Consult [next-agent.md](next-agent.md) for exact verification and prerequisites.

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
> status and verify T03 is merged into updated main. Implement T04 only on its
> own branch, preserving unrelated changes. Explain the plan, run its checks,
> update the handoff and affected docs, and open a draft PR against main. Do not
> merge, begin T05, or deploy cloud resources.

The handoff separates implemented behavior from verification and merge status.
Infrastructure activation and later task completion are not implied by this plan.
