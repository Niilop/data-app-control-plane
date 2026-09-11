# Product scope

## Agreed direction

A user orders a managed data application backed by an existing Git repository.
The platform connects code to responsible people, environments, approvals,
deployments, and operational results. Administrators manage platform teams and
access; external access automation is introduced explicitly by integration.

- GitHub is the first repository provider; GitHub Actions is the first CI/CD engine.
- Run the platform locally with FastAPI, a separate Python worker, PostgreSQL,
  and Streamlit. Use the developer's existing devstack where practical.
- Do not require Azure hosting for the platform. A real Databricks workspace can
  be used for a small, explicitly authorized integration demonstration.
- Keep the core usable when GitHub or Databricks is unreachable. Show last
  observed external state and its observation time.
- Keep business policies independent of hosting and provider credentials.

## Working assumptions for implementation

These unblock development and can be revised through the decision log:

1. The first application type is a Python batch-processing project containing one
   bundle and one synthetic-data job. It is not a Databricks-hosted web app.
2. One application maps to one repository and one bundle root. Multiple
   applications may share a repository only with distinct bundle roots.
3. Existing repositories must adopt the supported bundle contract before
   deployment. Registering a repository does not imply arbitrary code is deployable.
4. Start with one logical sandbox target, one real workspace when available, and
   one deployment executor per environment binding.
5. Local mode permits explicit self-approval, records it, and displays the policy.
   Organizational mode requires independent approval.
6. Start with platform membership/access. Git permissions, directory group
   creation, Databricks ACLs, and data grants are separately tracked future work.
7. New-project generation produces a downloadable artifact. Writing into an
   existing repository later happens through a reviewed PR; repository creation
   is deferred.

## Personas

| Persona | Responsibility |
|---|---|
| Data engineer | Request/register applications, develop code, request deployments, inspect permitted runs |
| Application owner | Maintain ownership and membership, approve platform access requests |
| Data owner | Named accountable person for the data; future data-access approval role |
| Deployment approver | Approve an exact revision and environment scope |
| Operator | Execute approved deployments, request runs, handle recovery |
| Platform administrator | Manage teams, role assignments, environments, and integration policy |

Owner and data owner are accountability relationships, not implicit grants of
every permission. A single developer can hold multiple roles in local mode.

## Local product demonstration

1. Sign in as a development user; create a team and assign application roles.
2. Register an existing GitHub repository reference, owner, data owner, and description.
3. Bind an approved sandbox environment and select a versioned Python bundle template.
4. Generate/download a project, or prepare a revision of an adopted repository.
5. Capture immutable source/artifact and configuration; inspect validation results.
6. Approve that exact revision; request a deployment and follow the durable operation.
7. Inspect a clearly labelled simulated deployment and simulated job result.
8. Request and approve another user's platform access; revoke it and demonstrate denial.
9. Inspect audit history and archive the application without destroying data.

GitHub integration adds real CI checks and observed workflow runs. The real
Databricks gate replaces simulated execution with an actual sandbox deployment
and synthetic-data job; simulation is never presented as proof of that gate.

## Scope boundaries

| Include initially | Defer |
|---|---|
| Teams and application membership | Directory synchronization and group provisioning |
| Revision-scoped deployment approvals | Enterprise change-management integration |
| One Python bundle template and GitHub workflows | Template marketplace and multiple workload types |
| Durable PostgreSQL operations | Redis queue, Service Bus, distributed microservices |
| Existing environment/resource references | Workspace creation and Terraform execution |
| Platform access request/revoke flow | Automated Git, workspace, and data grants |
| Local audit history and measured recovery | Protected audit export and enterprise retention |
| Explicit sandbox integration | Autonomous production deployment and billing automation |

## Completion gates

- **Local functional platform:** T01–T07 and T11; entire local demonstration works
  through the UI with no external credentials.
- **GitHub integration:** T08–T09; generated CI executes and exact-source workflow
  results are reconciled without a public local API.
- **Real sandbox:** T10; genuine external deployment/run IDs and synthetic result
  are visible. Requires a workspace and explicit execution authorization.
- **Recovery evidence:** T12; duplicates, lost leases, restarts, ambiguous dispatch,
  access revocation, and conflicting deployments are demonstrated.
- **Organizational pilot:** T13 design and subsequent approved implementation;
  identity, deployment enforcement, hosting, and operational ownership are verified.

There is no promised zero-cost cloud execution. The local gate must remain usable
without it, and current provider costs/limits must be checked before paid work.
