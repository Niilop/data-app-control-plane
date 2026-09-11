**Project Goal**
Build a **self-service Databricks application management platform**: a developer registers an application, generates a DAB project, deploys it to an approved environment, and follows its operational status.

Start as a fully functional, single-developer application running locally. Extend it through configurable integrations, without rewriting the business logic. This is an initial requirements baseline, not a requirement to implement every enterprise feature immediately.

**1. Scope**
The first complete version should support:
- Registering applications with a stable ID, description, owner, repository, and lifecycle status.
- Selecting a versioned Python/DAB template and generating a usable project.
- Configuring environments and referencing existing Databricks workspaces.
- Validating, approving, and deploying a specific application revision.
- Listing deployments, triggering permitted job runs, and viewing execution results.
- Recording who requested, approved, and executed each change.
- Archiving applications without automatically deleting their data.

Initially exclude automatic workspace creation, a custom data-processing engine, enterprise catalog replacement, and billing automation. Your platform manages applications; **Databricks executes their processing logic**.

**2. Architecture**
Use a **modular monolith with independently runnable API and worker processes**. Share Python application logic, but give processes different credentials and responsibilities.

```text
UI / CLI → FastAPI → Application services → PostgreSQL
                              ↓
                       Durable operations
                              ↓
                           Worker
                              ↓
             Git / DAB CLI / Databricks / Infrastructure
```

FastAPI should authenticate, authorize, validate, and persist requests. Workers perform long-running external operations. The browser must never receive deployment credentials. Serve normal application state from PostgreSQL rather than calling every external system during each page request.

**3. Modules**
| Module | Initial Requirements | Extension Point |
|---|---|---|
| Identity and authorization | Development users; application ownership; viewer/developer/approver/operator roles | Entra login and directory-group mappings |
| Application registry | Applications, environments, repositories, resource references, lifecycle state | Team quotas and organizational policy |
| Template management | Versioned templates, validated inputs, project generation, generated-project tests | Additional approved application types |
| Deployment management | Validate DAB, capture immutable revision/artifact, approve, deploy, record results | Corporate CI/CD and promotion gates |
| Operations | Durable execution, retries, cancellation requests, progress and errors | Multiple workers and external messaging |
| Databricks integration | Workspace validation, deployment references, job submission and status | Multiple workspaces and accounts |
| Infrastructure integration | Register pre-existing resources; explicitly simulated provisioning | Reviewed Terraform execution |
| Audit and telemetry | Actor/action/target/outcome records, structured logs, correlation IDs | Central monitoring and protected audit export |

**4. Data and Workflow Contracts**
Persist users or external identity references, teams, applications, environment bindings, template versions, deployment revisions, approvals, operations, attempts, job runs, and audit events. Use database migrations from the first version.

Every deployment must reference an **immutable commit or artifact digest**, template version, configuration snapshot, target, and requester. An approval applies to that exact revision and scope; editing them requires renewed approval.

Separate operation status from resource status: a failed provisioning operation can leave partially created resources. Return `202 Accepted` with an operation ID for asynchronous commands, and provide paginated status/history endpoints. Record external execution IDs immediately when available.

**5. Reliability and Scalability**
- **Durable dispatch:** insert the operation and related state change in one database transaction. Introduce a transactional outbox when publishing to an external broker.
- **Safe worker claiming:** use atomic claims, leases, heartbeats, and ownership checks. Reclaim abandoned work, but prevent a stale worker from committing results after losing its lease.
- **Idempotent execution:** assume at-least-once delivery. Use request keys and external resource identifiers; after ambiguous timeouts, reconcile external state before retrying.
- **Controlled concurrency:** serialize conflicting changes to the same application/environment. Limit parallel work per workspace and respect provider rate limits.
- **Recoverable failures:** classify retryable and terminal failures, apply bounded exponential backoff, and expose manual recovery. Cancellation is best-effort; it does not imply rollback.
- **Horizontal growth:** keep API processes stateless, artifacts outside process-local storage, and worker execution isolated. Add replicas only after measuring demand.
- **Measured performance:** test API latency, operation throughput, queue age, database contention, and worker recovery against a declared workload. Set concrete targets during implementation rather than promising arbitrary scale.

**6. Local-to-Azure Profiles**
| Capability | Local | Minimal Azure | Later Organization |
|---|---|---|---|
| API and worker | Docker Compose | Container Apps and worker/jobs | Same service with replicas and controlled execution pools |
| Registry and queue | PostgreSQL container | Managed PostgreSQL; retain database queue | Service Bus if throughput or operational needs justify it |
| Identity | Explicit development authentication | Entra integration when needed | Enterprise groups, Conditional Access, privileged workflows |
| Artifacts and secrets | Local artifact directory; developer credential tooling | Blob Storage, managed identities, Key Vault where needed | Corporate registries, federation, centralized policies |
| Databricks and Git | Simulation plus optional real sandbox; local Git | One existing workspace and Git provider | Environment-specific identities, workspaces, and corporate CI |

Configuration selects adapters at startup. Production profiles must reject development authentication, simulated provisioning, and unsafe defaults. **Changing profiles does not migrate data or provision infrastructure.** Azure Functions are optional for lightweight event handlers; do not force long-running DAB/Terraform execution into HTTP functions.

**7. Security Requirements**
Enforce authorization on every API operation and recheck sensitive authorization before queued work executes. Separate requester, deployer, runtime, and storage identities; avoid subscription-wide privileges. Keep secrets out of Git, operation payloads, browser responses, and logs.

Treat generated projects and repository code as executable, potentially unsafe input. Use approved templates, validated parameters, argument-array subprocess calls, timeouts, isolated execution, and restricted credentials. A general API worker must not run arbitrary user code with infrastructure-administrator permissions. Build a fresh independent template; do not copy proprietary OPDP libraries or documentation into a personal project without permission.

**8. Testing and Agent-Assisted Development**
Use a Python template with FastAPI, Pydantic settings, SQLAlchemy/Alembic, PostgreSQL, pytest, linting, type checking, and dependency locking. Define adapter interfaces only for integrations actually being implemented.

For coding agents, keep a versioned requirements document, architecture decisions, API contracts, and repository instructions. Give each task one vertical slice, explicit exclusions, and executable acceptance criteria. Require tests with implementation, human review for identity/infrastructure changes, and no autonomous production deployment or secret handling. Agents should never make failing checks pass by weakening authorization or silently substituting simulations.

**9. Delivery Gates**
| Phase | Completion Criteria |
|---|---|
| Local functional platform | Register an application, generate a project, approve an operation, execute a clearly labelled simulation, and inspect history through the UI |
| Real sandbox integration | Deploy a generated DAB project to an existing workspace, run a synthetic-data job, and display the genuine external result |
| Recovery and isolation | Demonstrate duplicate-request handling, restart recovery, ambiguous-timeout reconciliation, authorization denial, and concurrent-operation protection |
| Minimal Azure deployment | Run the same core remotely; prove database restore, identity configuration, telemetry, and cost controls |
| Organizational pilot | Add corporate identity/CI adapters, reviewed provisioning, access revocation, operational ownership, and security approval for one team |

**Recommended first milestone:** application registration → DAB generation → validation → sandbox deployment → job status. Complete that path before adding more cloud services. It gives you a useful application, exposes the real integration problems, and establishes a foundation that can grow beyond a learning project.