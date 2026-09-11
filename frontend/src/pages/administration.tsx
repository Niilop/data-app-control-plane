import { useState } from "react";
import { Activity, ArrowRight, Network, Users, UserRound } from "lucide-react";
import { api } from "../api";
import {
  ActionForm,
  AddButton,
  Badge,
  date,
  Dialog,
  ErrorNotice,
  Field,
  label,
  Loading,
  number,
  PageHeader,
  Paged,
  RefreshButton,
  Status,
  text,
} from "../components";
import { ReferenceSelect } from "../ReferenceSelect";
import { useData, useResource, useSession } from "../state";
import type { Audit, Binding, Environment, Member, Team } from "../types";

export function Teams() {
  const { user } = useSession();
  const { refresh, notify } = useData();
  const [create, setCreate] = useState(false);
  const [team, setTeam] = useState<Team | null>(null);
  return (
    <>
      <PageHeader
        eyebrow="PEOPLE & OWNERSHIP"
        title="Teams"
        description="Organize the people responsible for your applications."
        actions={
          <>
            <RefreshButton />
            {user?.is_platform_admin && (
              <AddButton onClick={() => setCreate(true)}>Create team</AddButton>
            )}
          </>
        }
      />
      <section className="panel">
        <Paged<Team>
          path="/api/v1/teams"
          empty="No teams yet"
          description="An administrator can create a team and add its members."
        >
          {(items) => (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Team</th>
                    <th>Created</th>
                    <th>
                      <span className="sr-only">Members</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <span className="cell-title">
                          <Users size={18} />
                          {item.name}
                        </span>
                      </td>
                      <td className="muted">{date(item.created_at)}</td>
                      <td>
                        <button
                          className="text-button"
                          aria-label={`View members of ${item.name}`}
                          onClick={() => setTeam(item)}
                        >
                          View members
                          <ArrowRight size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Paged>
      </section>
      {create && (
        <Dialog title="Create a team" onClose={() => setCreate(false)}>
          <ActionForm
            submitLabel="Create team"
            onCancel={() => setCreate(false)}
            submit={async (data) => {
              const result = await api<Team>("/api/v1/teams", {
                method: "POST",
                body: { name: text(data, "name") },
              });
              setCreate(false);
              setTeam(result);
              refresh();
              notify("Team created. Add its members below.");
            }}
          >
            <Field label="Team name">
              <input
                name="name"
                required
                maxLength={100}
                placeholder="Data engineering"
              />
            </Field>
          </ActionForm>
        </Dialog>
      )}
      {team && (
        <TeamMembers key={team.id} team={team} onClose={() => setTeam(null)} />
      )}
    </>
  );
}
function TeamMembers({ team, onClose }: { team: Team; onClose: () => void }) {
  const { user } = useSession();
  const { refresh, notify } = useData();
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const path = `/api/v1/teams/${team.id}/members`;
  return (
    <Dialog
      title={`${team.name} members`}
      description="Membership alone does not grant access to every application."
      onClose={onClose}
    >
      <ErrorNotice error={error} />
      <Paged<Member> path={path} empty="This team has no members">
        {(items) => (
          <ul className="member-list">
            {items.map((member) => (
              <li key={member.id}>
                <span className="cell-title">
                  <UserRound size={16} />
                  {member.user_id === user?.id
                    ? `${user.username} (you)`
                    : `User #${member.user_id}`}
                </span>
                {user?.is_platform_admin && (
                  <button
                    className="text-button danger"
                    disabled={busy}
                    aria-label={`Remove user ${member.user_id}`}
                    onClick={async () => {
                      setBusy(true);
                      setError(null);
                      try {
                        await api(`${path}/${member.user_id}`, {
                          method: "DELETE",
                        });
                        refresh();
                        notify("Team member removed.");
                      } catch (e) {
                        setError(e as Error);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Paged>
      {user?.is_platform_admin && (
        <div className="form-section">
          <h3>Add a member</h3>
          <ActionForm
            submitLabel="Add member"
            submit={async (data) => {
              await api(path, {
                method: "POST",
                body: { user_id: number(data, "user_id") },
              });
              refresh();
              notify("Team member added.");
            }}
          >
            <Field
              label="User ID"
              hint={`Your ID is ${user.id}. Add yourself before registering an application for this team.`}
            >
              <input
                type="number"
                name="user_id"
                min={1}
                required
                defaultValue={user.id}
              />
            </Field>
          </ActionForm>
        </div>
      )}
    </Dialog>
  );
}
function EnvironmentFields({ environment }: { environment?: Environment }) {
  return (
    <>
      <Field label="Environment name">
        <input
          name="name"
          required
          maxLength={100}
          defaultValue={environment?.name}
          placeholder="Local sandbox"
        />
      </Field>
      <Field
        label="Workspace reference"
        hint="Local simulated reference, such as simulated://sandbox."
      >
        <input
          name="workspace_ref"
          required
          maxLength={100}
          pattern="simulated://[a-z][a-z0-9-]{0,62}"
          defaultValue={environment?.workspace_ref || "simulated://sandbox"}
        />
      </Field>
      <Field
        label="Approved bundle targets"
        hint="Comma-separated lowercase target names, such as sandbox, dev."
      >
        <textarea
          name="targets"
          required
          rows={2}
          defaultValue={
            environment?.allowed_bundle_targets.join(", ") || "sandbox"
          }
        />
      </Field>
      <label className="checkbox">
        <input
          type="checkbox"
          name="enabled"
          defaultChecked={environment?.enabled ?? true}
        />
        <span>
          Environment enabled
          <small>Allow applications to use this environment.</small>
        </span>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          name="allow_self_approval"
          defaultChecked={environment?.allow_self_approval ?? false}
        />
        <span>
          Allow local self-approval
          <small>
            Explicit policy for future approvals. Disabled by default.
          </small>
        </span>
      </label>
      <div className="alert">
        Execution is simulated. No external workspace is created.
      </div>
    </>
  );
}
function environmentData(data: FormData) {
  return {
    name: text(data, "name"),
    workspace_ref: text(data, "workspace_ref"),
    allowed_executor: "simulated",
    allowed_bundle_targets: text(data, "targets")
      .split(/[\s,]+/)
      .filter(Boolean),
    enabled: data.has("enabled"),
    allow_self_approval: data.has("allow_self_approval"),
  };
}
export function Environments() {
  const { user } = useSession();
  const { refresh, notify } = useData();
  const [edit, setEdit] = useState<Environment | "new" | null>(null);
  return (
    <>
      <PageHeader
        eyebrow="APPROVED TARGETS"
        title="Environments"
        description="Control where applications may run and the policy they follow."
        actions={
          <>
            <RefreshButton />
            {user?.is_platform_admin && (
              <AddButton onClick={() => setEdit("new")}>
                Create environment
              </AddButton>
            )}
          </>
        }
      />
      <Paged<Environment>
        path="/api/v1/environments"
        empty="No environments available"
        description="Administrators can create a simulated environment. Members see environments linked to their applications."
      >
        {(items, loading) => (
          <div className="environment-grid">
            {items.map((env) => (
              <section className="panel environment-card" key={env.id}>
                <div className="card-heading">
                  <span className="app-icon">
                    <Network size={21} />
                  </span>
                  <Badge tone={env.enabled ? "green" : ""}>
                    {env.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </div>
                <h2>{env.name}</h2>
                <code>{env.workspace_ref}</code>
                <div className="target-list">
                  {env.allowed_bundle_targets.map((target) => (
                    <Badge key={target}>{target}</Badge>
                  ))}
                </div>
                <dl>
                  <dt>Execution</dt>
                  <dd>
                    <Badge tone="blue">Simulated</Badge>
                  </dd>
                  <dt>Self-approval</dt>
                  <dd>
                    {env.allow_self_approval ? "Allowed locally" : "Disabled"}
                  </dd>
                  <dt>Policy version</dt>
                  <dd>{env.version}</dd>
                </dl>
                {user?.is_platform_admin && (
                  <button
                    className="button secondary wide"
                    aria-label={`Edit ${env.name}`}
                    disabled={loading}
                    onClick={() => setEdit(env)}
                  >
                    Edit environment
                  </button>
                )}
              </section>
            ))}
          </div>
        )}
      </Paged>
      {edit && (
        <Dialog
          title={edit === "new" ? "Create an environment" : "Edit environment"}
          description={
            edit === "new"
              ? "Define an approved simulated target."
              : `Editing policy version ${edit.version}. Changes invalidate existing binding versions.`
          }
          onClose={() => setEdit(null)}
        >
          <ActionForm
            submitLabel={edit === "new" ? "Create environment" : "Save changes"}
            onCancel={() => setEdit(null)}
            submit={async (data) => {
              await api(
                `/api/v1/environments${edit === "new" ? "" : `/${edit.id}`}`,
                {
                  method: edit === "new" ? "POST" : "PATCH",
                  body: {
                    ...environmentData(data),
                    ...(edit === "new"
                      ? {}
                      : { expected_version: edit.version }),
                  },
                },
              );
              setEdit(null);
              refresh();
              notify("Environment saved.");
            }}
          >
            <EnvironmentFields
              environment={edit === "new" ? undefined : edit}
            />
          </ActionForm>
        </Dialog>
      )}
    </>
  );
}
function ConfigFields({ config }: { config?: Binding["config"] }) {
  return (
    <div className="form-grid">
      <Field label="Synthetic row count">
        <input
          type="number"
          name="synthetic_row_count"
          required
          min={1}
          max={10000}
          step={1}
          defaultValue={config?.synthetic_row_count || 100}
        />
      </Field>
      <Field label="Maximum runtime (seconds)">
        <input
          type="number"
          name="max_runtime_seconds"
          required
          min={1}
          max={3600}
          step={1}
          defaultValue={config?.max_runtime_seconds || 300}
        />
      </Field>
    </div>
  );
}
function configData(data: FormData) {
  return {
    schema_version: 1,
    synthetic_row_count: number(data, "synthetic_row_count"),
    max_runtime_seconds: number(data, "max_runtime_seconds"),
  };
}
export function Bindings({
  applicationId,
  canManage,
}: {
  applicationId: string;
  canManage: boolean;
}) {
  const path = `/api/v1/applications/${applicationId}/bindings`;
  const [edit, setEdit] = useState<Binding | "new" | null>(null);
  return (
    <>
      <div className="section-heading standalone">
        <div>
          <h2>Environment bindings</h2>
          <p>Approved targets and application-specific configuration.</p>
        </div>
        {canManage && (
          <AddButton onClick={() => setEdit("new")}>Bind environment</AddButton>
        )}
      </div>
      <Paged<Binding>
        path={path}
        empty="No environments bound"
        description="An administrator can connect this application to an approved environment."
      >
        {(items, loading) => (
          <div className="environment-grid">
            {items.map((binding) => (
              <section className="panel environment-card" key={binding.id}>
                <div className="card-heading">
                  <h2>{binding.environment.name}</h2>
                  <Badge tone={binding.usable ? "green" : "amber"}>
                    {binding.usable ? "Available" : "Unavailable"}
                  </Badge>
                </div>
                <p className="muted">{binding.environment.workspace_ref}</p>
                <div className="target-list">
                  <Badge tone="blue">Simulated</Badge>
                  <Badge>{binding.bundle_target}</Badge>
                </div>
                <dl>
                  <dt>Synthetic rows</dt>
                  <dd>{binding.config.synthetic_row_count.toLocaleString()}</dd>
                  <dt>Runtime limit</dt>
                  <dd>{binding.config.max_runtime_seconds} seconds</dd>
                  <dt>Binding / policy version</dt>
                  <dd>
                    {binding.version} / {binding.environment.version}
                  </dd>
                  <dt>Self-approval</dt>
                  <dd>
                    {binding.environment.allow_self_approval
                      ? "Allowed locally"
                      : "Disabled"}
                  </dd>
                </dl>
                {!binding.usable && (
                  <p className="inline-warning">
                    The environment, target or application is currently
                    unavailable.
                  </p>
                )}
                {canManage && (
                  <button
                    className="button secondary wide"
                    disabled={loading || !binding.environment.enabled}
                    aria-label={`Edit binding for ${binding.environment.name}`}
                    onClick={() => setEdit(binding)}
                  >
                    Edit binding
                  </button>
                )}
              </section>
            ))}
          </div>
        )}
      </Paged>
      {edit && (
        <BindingEditor
          applicationId={applicationId}
          edit={edit}
          onClose={() => setEdit(null)}
        />
      )}
    </>
  );
}
function BindingEditor({
  applicationId,
  edit,
  onClose,
}: {
  applicationId: string;
  edit: Binding | "new";
  onClose: () => void;
}) {
  const [environmentId, setEnvironmentId] = useState(
    edit === "new" ? "" : edit.environment_id,
  );
  const resource = useResource<Environment>(
    environmentId ? `/api/v1/environments/${environmentId}` : null,
  );
  const environment = resource.data;
  const { refresh, notify } = useData();
  return (
    <Dialog
      title={edit === "new" ? "Bind an environment" : "Edit binding"}
      description={
        edit === "new"
          ? "Choose an approved environment and bundle target."
          : `Editing binding version ${edit.version}.`
      }
      onClose={onClose}
    >
      <ActionForm
        submitLabel={edit === "new" ? "Create binding" : "Save binding"}
        disabled={!environment?.enabled || resource.loading}
        onCancel={onClose}
        submit={async (data) => {
          await api(
            `/api/v1/applications/${applicationId}/bindings${edit === "new" ? "" : `/${edit.id}`}`,
            {
              method: edit === "new" ? "POST" : "PATCH",
              body: {
                ...(edit === "new"
                  ? { environment_id: environmentId }
                  : { expected_version: edit.version }),
                bundle_target: text(data, "bundle_target"),
                config: configData(data),
              },
            },
          );
          onClose();
          refresh();
          notify("Environment binding saved.");
        }}
      >
        {edit === "new" && (
          <ReferenceSelect
            path="/api/v1/environments"
            name="environment_id"
            label="Environment"
            value={environmentId}
            onChange={setEnvironmentId}
          />
        )}
        <ErrorNotice error={resource.error} />
        {environmentId && resource.loading && !environment ? (
          <Loading />
        ) : (
          environment && (
            <>
              <Field label="Bundle target">
                <select
                  key={environmentId}
                  name="bundle_target"
                  required
                  defaultValue={edit === "new" ? "" : edit.bundle_target}
                >
                  <option value="">Select an approved target</option>
                  {environment.allowed_bundle_targets.map((target) => (
                    <option key={target}>{target}</option>
                  ))}
                </select>
              </Field>
              {!environment.enabled && (
                <div className="alert error">
                  This environment is disabled. An administrator must enable it
                  before use.
                </div>
              )}
            </>
          )
        )}
        <ConfigFields config={edit === "new" ? undefined : edit.config} />
      </ActionForm>
    </Dialog>
  );
}
export function AuditList({ path }: { path: string }) {
  return (
    <Paged<Audit>
      path={path}
      empty="No activity recorded"
      description="Changes and worker observations will appear here."
    >
      {(items) => (
        <ol className="timeline">
          {items.map((event) => (
            <li key={event.id}>
              <span className="timeline-icon">
                <Activity size={16} />
              </span>
              <div className="timeline-content">
                <div className="timeline-heading">
                  <strong>{label(event.action.replaceAll(".", " · "))}</strong>
                  <time>{date(event.created_at)}</time>
                </div>
                <p>
                  {event.actor_user_id
                    ? `User #${event.actor_user_id}`
                    : label(event.actor_kind)}
                  <span className="separator">·</span>
                  <Status value={event.outcome} />
                </p>
                <details>
                  <summary>View event details</summary>
                  <dl>
                    <dt>Target</dt>
                    <dd className="break-word">
                      {event.target_type} · {event.target_id}
                    </dd>
                    <dt>Request ID</dt>
                    <dd className="break-word">{event.request_id}</dd>
                  </dl>
                  <pre>{JSON.stringify(event.details, null, 2)}</pre>
                </details>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Paged>
  );
}
export function ActivityPage() {
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE HISTORY"
        title="Activity"
        description="An attributable record of changes across your workspace."
        actions={<RefreshButton />}
      />
      <section className="panel">
        <AuditList path="/api/v1/audit-events" />
      </section>
    </>
  );
}
export function Account() {
  const { user } = useSession();
  const health = useResource<{ status: string }>("/ready");
  return (
    <>
      <PageHeader
        eyebrow="YOUR PROFILE"
        title="Account"
        description="Your identity in this local workspace."
      />
      <div className="detail-grid">
        <section className="panel">
          <div className="section-heading">
            <h2>Profile</h2>
            <Badge>
              {user?.is_platform_admin ? "Administrator" : "Member"}
            </Badge>
          </div>
          <div className="panel-body">
            <dl>
              <dt>Username</dt>
              <dd>{user?.username}</dd>
              <dt>Email</dt>
              <dd>{user?.email}</dd>
              <dt>User ID</dt>
              <dd>{user?.id}</dd>
              <dt>Account</dt>
              <dd>
                <Status value="active" />
              </dd>
            </dl>
          </div>
        </section>
        <section className="panel">
          <div className="section-heading">
            <h2>Workspace status</h2>
            <RefreshButton />
          </div>
          <div className="panel-body">
            <ErrorNotice error={health.error} />
            {health.loading ? (
              <Loading />
            ) : (
              health.data && (
                <>
                  <Badge tone="green">API and worker ready</Badge>
                  <p className="muted">
                    The database is reachable and a worker has reported
                    recently.
                  </p>
                </>
              )
            )}
            <p className="form-hint">
              Execution is explicitly simulated. No external provider is active.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
