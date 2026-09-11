import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  ArrowUpRight,
  Boxes,
  Pencil,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api } from "../api";
import {
  ActionForm,
  AddButton,
  Badge,
  date,
  Dialog,
  Empty,
  ErrorNotice,
  Field,
  Loading,
  number,
  PageHeader,
  Paged,
  RefreshButton,
  Status,
  text,
} from "../components";
import { ReferenceSelect } from "../ReferenceSelect";
import { useData, usePage, useResource, useSession } from "../state";
import type { Application, Capabilities, Role } from "../types";
import { AuditList, Bindings } from "./administration";
import { Operations } from "./operations";

function MetadataFields({ application }: { application?: Application }) {
  return (
    <>
      <Field label="Application name">
        <input
          name="name"
          required
          maxLength={200}
          defaultValue={application?.name}
          placeholder="e.g. Customer analytics"
        />
      </Field>
      <Field
        label="Description"
        hint="A short description of what this application does."
      >
        <textarea
          name="description"
          maxLength={4000}
          defaultValue={application?.description}
          rows={3}
        />
      </Field>
      <Field
        label="GitHub repository URL"
        hint="An existing GitHub repository. Access is not verified at registration."
      >
        <input
          name="repository_url"
          type="url"
          required
          maxLength={500}
          defaultValue={application?.repository_url}
          placeholder="https://github.com/your-team/your-repository"
        />
      </Field>
      <Field
        label="Bundle root"
        hint="Relative path in the repository; use . for its root."
      >
        <input
          name="bundle_root"
          required
          maxLength={500}
          defaultValue={application?.bundle_root || "."}
        />
      </Field>
    </>
  );
}
function metadata(data: FormData) {
  return {
    name: text(data, "name"),
    description: text(data, "description"),
    repository_url: text(data, "repository_url"),
    bundle_root: text(data, "bundle_root"),
  };
}
function OwnershipFields({ application }: { application?: Application }) {
  const { user } = useSession();
  const [team, setTeam] = useState(application?.owning_team_id || "");
  return (
    <>
      <ReferenceSelect
        path="/api/v1/teams"
        name="owning_team_id"
        label="Owning team"
        value={team}
        onChange={setTeam}
      />
      <div className="form-grid">
        <Field label="Owner user ID" hint="Accountable application owner.">
          <input
            type="number"
            name="owner_user_id"
            required
            min={1}
            step={1}
            defaultValue={application?.owner_user_id || user?.id}
          />
        </Field>
        <Field label="Data owner user ID" hint="Accountable owner of the data.">
          <input
            type="number"
            name="data_owner_user_id"
            required
            min={1}
            step={1}
            defaultValue={application?.data_owner_user_id || user?.id}
          />
        </Field>
      </div>
      <p className="form-hint">
        Your user ID is {user?.id}. Other members can find theirs in Account.
      </p>
    </>
  );
}
function ownership(data: FormData) {
  return {
    owning_team_id: text(data, "owning_team_id"),
    owner_user_id: number(data, "owner_user_id"),
    data_owner_user_id: number(data, "data_owner_user_id"),
  };
}
export function Applications() {
  const [create, setCreate] = useState(false);
  const [filter, setFilter] = useState("");
  const page = usePage<Application>("/api/v1/applications");
  const navigate = useNavigate();
  const { notify, refresh } = useData();
  const items =
    page.data?.items.filter((app) =>
      `${app.name} ${app.slug}`.toLowerCase().includes(filter.toLowerCase()),
    ) || [];
  return (
    <>
      <PageHeader
        eyebrow="APPLICATION REGISTRY"
        title="Applications"
        description="Your data applications, their owners, and where they run."
        actions={
          <AddButton onClick={() => setCreate(true)}>
            Register application
          </AddButton>
        }
      />
      <section className="panel">
        <div className="panel-toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Filter applications on this page"
              placeholder="Filter this page by name or slug…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <RefreshButton />
        </div>
        <ErrorNotice error={page.error} />
        {page.loading && !page.data ? (
          <Loading />
        ) : (
          !page.error &&
          (items.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Application</th>
                    <th>Status</th>
                    <th>Owner</th>
                    <th>Updated</th>
                    <th>
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((app) => (
                    <tr key={app.id}>
                      <td>
                        <Link
                          className="application-link"
                          to={`/applications/${app.id}`}
                        >
                          <span className="app-icon">
                            <Boxes size={20} />
                          </span>
                          <span>
                            <strong>{app.name}</strong>
                            <small>{app.slug}</small>
                          </span>
                        </Link>
                      </td>
                      <td>
                        <Status value={app.lifecycle} />
                      </td>
                      <td>
                        <span className="owner-chip">
                          User #{app.owner_user_id}
                        </span>
                      </td>
                      <td className="muted">{date(app.updated_at)}</td>
                      <td>
                        <Link
                          className="icon-button"
                          aria-label={`Open ${app.name}`}
                          to={`/applications/${app.id}`}
                        >
                          <ArrowUpRight size={17} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title={
                filter
                  ? "No matches on this page"
                  : "Your first application starts here"
              }
              action={
                !filter && (
                  <AddButton onClick={() => setCreate(true)}>
                    Register application
                  </AddButton>
                )
              }
            >
              {filter
                ? "Try another name or move to another page."
                : "Register a repository, assign ownership, and bring its history into one place."}
            </Empty>
          ))
        )}
        {page.data && (
          <div className="pagination">
            <span>
              {items.length} of {page.data.items.length} applications on this
              page
            </span>
            <div>
              <button
                className="button small secondary"
                onClick={page.previous}
                disabled={page.page === 1 || page.loading}
              >
                Previous
              </button>
              <span>Page {page.page}</span>
              <button
                className="button small secondary"
                onClick={page.next}
                disabled={!page.data.next_cursor || page.loading}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </section>
      <div className="footnote">
        <ShieldCheck size={17} />
        Only applications you have access to appear here.
      </div>
      {create && (
        <Dialog
          title="Register an application"
          description="Connect a repository with its accountable owners."
          onClose={() => setCreate(false)}
        >
          <ActionForm
            submitLabel="Register application"
            onCancel={() => setCreate(false)}
            submit={async (data) => {
              const result = await api<Application>("/api/v1/applications", {
                method: "POST",
                body: {
                  slug: text(data, "slug"),
                  ...metadata(data),
                  ...ownership(data),
                },
              });
              notify("Application registered.");
              refresh();
              navigate(`/applications/${result.id}`);
            }}
          >
            <Field
              label="Slug"
              hint="A unique name using lowercase letters, numbers and hyphens."
            >
              <input
                name="slug"
                pattern="[a-z0-9]+(-[a-z0-9]+)*"
                required
                maxLength={63}
                placeholder="customer-analytics"
              />
            </Field>
            <MetadataFields />
            <OwnershipFields />
          </ActionForm>
        </Dialog>
      )}
    </>
  );
}
export function ApplicationDetail() {
  const { id } = useParams();
  return <ApplicationContent key={id} id={id!} />;
}
function ApplicationContent({ id }: { id: string }) {
  const path = `/api/v1/applications/${id}`;
  const resource = useResource<Application>(path);
  const permissions = useResource<Capabilities>(`${path}/capabilities`);
  const [tab, setTab] = useState("Overview");
  const [edit, setEdit] = useState<{
    kind: "metadata" | "ownership";
    snapshot: Application;
  } | null>(null);
  const { refresh, notify } = useData();
  const app = resource.data;
  const caps = permissions.data;
  if (resource.error)
    return (
      <>
        <Link className="back-link" to="/applications">
          <ArrowLeft size={16} />
          Applications
        </Link>
        <ErrorNotice error={resource.error} />
        <RefreshButton />
      </>
    );
  if (!app) return <Loading />;
  return (
    <>
      <Link className="back-link" to="/applications">
        <ArrowLeft size={16} />
        All applications
      </Link>
      <PageHeader
        title={app.name}
        eyebrow={app.slug}
        description={
          app.description ||
          "Application ownership, configuration and operation history."
        }
        actions={
          <>
            <Status value={app.lifecycle} />
            <RefreshButton />
            {caps?.edit_metadata && (
              <button
                className="button primary"
                onClick={() => setEdit({ kind: "metadata", snapshot: app })}
              >
                <Pencil size={16} />
                Edit application
              </button>
            )}
          </>
        }
      />
      <ErrorNotice error={permissions.error} />
      <div className="tabs" role="tablist" aria-label="Application sections">
        {["Overview", "Environments", "Access", "Operations", "Activity"].map(
          (name) => (
            <button
              key={name}
              role="tab"
              id={`tab-${name}`}
              aria-controls="application-panel"
              tabIndex={tab === name ? 0 : -1}
              aria-selected={tab === name}
              onClick={() => setTab(name)}
              onKeyDown={(event) => {
                const tabs = [
                  "Overview",
                  "Environments",
                  "Access",
                  "Operations",
                  "Activity",
                ];
                const index = tabs.indexOf(name);
                const next =
                  event.key === "ArrowRight"
                    ? (index + 1) % tabs.length
                    : event.key === "ArrowLeft"
                      ? (index + tabs.length - 1) % tabs.length
                      : event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? tabs.length - 1
                          : -1;
                if (next >= 0) {
                  event.preventDefault();
                  setTab(tabs[next]);
                  document.getElementById(`tab-${tabs[next]}`)?.focus();
                }
              }}
            >
              {name}
            </button>
          ),
        )}
      </div>
      <div
        id="application-panel"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        tabIndex={0}
      >
        {tab === "Overview" && (
          <div className="detail-grid">
            <section className="panel">
              <div className="section-heading">
                <h2>Repository</h2>
                <Badge tone="amber">
                  {app.repository_verified_at ? "Verified" : "Unverified"}
                </Badge>
              </div>
              <div className="panel-body">
                <a
                  className="repository-link"
                  href={app.repository_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {app.repository_url.replace("https://github.com/", "")}
                  <ArrowUpRight size={16} />
                </a>
                <p className="muted">
                  Registration records the repository reference. It does not
                  check access or contents.
                </p>
                <dl>
                  <dt>Bundle root</dt>
                  <dd>
                    <code>{app.bundle_root}</code>
                  </dd>
                  <dt>Registered</dt>
                  <dd>{date(app.created_at)}</dd>
                  <dt>Version</dt>
                  <dd>{app.version}</dd>
                </dl>
              </div>
            </section>
            <section className="panel">
              <div className="section-heading">
                <h2>Ownership</h2>
                {caps?.manage_access && (
                  <button
                    className="text-button"
                    onClick={() =>
                      setEdit({ kind: "ownership", snapshot: app })
                    }
                  >
                    Manage ownership
                  </button>
                )}
              </div>
              <div className="panel-body">
                <dl>
                  <dt>Owning team</dt>
                  <dd className="break-word">{app.owning_team_id}</dd>
                  <dt>Application owner</dt>
                  <dd>User #{app.owner_user_id}</dd>
                  <dt>Data owner</dt>
                  <dd>User #{app.data_owner_user_id}</dd>
                </dl>
              </div>
            </section>
            <section className="panel full-width">
              <div className="section-heading">
                <h2>Application identity</h2>
              </div>
              <div className="panel-body">
                <dl>
                  <dt>Application ID</dt>
                  <dd>
                    <code className="break-word">{app.id}</code>
                  </dd>
                  <dt>Execution</dt>
                  <dd>
                    <Badge tone="blue">Simulated</Badge>
                  </dd>
                </dl>
              </div>
            </section>
          </div>
        )}
        {tab === "Environments" && (
          <Bindings applicationId={id} canManage={!!caps?.manage_bindings} />
        )}
        {tab === "Access" && (
          <Access applicationId={id} canManage={!!caps?.manage_access} />
        )}
        {tab === "Operations" && (
          <Operations applicationId={id} canOperate={!!caps?.operate} />
        )}
        {tab === "Activity" && (
          <section className="panel">
            <AuditList path={`${path}/audit-events`} />
          </section>
        )}
      </div>
      {edit && (
        <Dialog
          title={
            edit.kind === "metadata" ? "Edit application" : "Manage ownership"
          }
          description={`Editing version ${edit.snapshot.version}. Concurrent changes will require a refresh.`}
          onClose={() => setEdit(null)}
        >
          <ActionForm
            onCancel={() => setEdit(null)}
            submit={async (data) => {
              await api(path, {
                method: "PATCH",
                body: {
                  expected_version: edit.snapshot.version,
                  ...(edit.kind === "metadata"
                    ? metadata(data)
                    : ownership(data)),
                },
              });
              notify("Application updated.");
              setEdit(null);
              refresh();
            }}
          >
            {edit.kind === "metadata" ? (
              <MetadataFields application={edit.snapshot} />
            ) : (
              <OwnershipFields application={edit.snapshot} />
            )}
          </ActionForm>
        </Dialog>
      )}
    </>
  );
}
function Access({
  applicationId,
  canManage,
}: {
  applicationId: string;
  canManage: boolean;
}) {
  const [assign, setAssign] = useState(false);
  const [subject, setSubject] = useState("user");
  const [team, setTeam] = useState("");
  const [remove, setRemove] = useState<Role | null>(null);
  const { refresh, notify } = useData();
  const path = `/api/v1/applications/${applicationId}/roles`;
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Application access</h2>
          <p>Explicit roles for people and teams.</p>
        </div>
        {canManage && (
          <AddButton onClick={() => setAssign(true)}>Assign role</AddButton>
        )}
      </div>
      <Paged<Role> path={path} empty="No role assignments">
        {(items) => (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Role</th>
                  <th>Assigned</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((role) => (
                  <tr key={role.id}>
                    <td className="break-word">
                      {role.user_id
                        ? `User #${role.user_id}`
                        : `Team ${role.team_id}`}
                    </td>
                    <td>
                      <Badge>{role.role}</Badge>
                    </td>
                    <td>{date(role.created_at)}</td>
                    <td>
                      {canManage && (
                        <button
                          className="text-button danger"
                          aria-label={`Remove ${role.role} for ${role.user_id || role.team_id}`}
                          onClick={() => setRemove(role)}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Paged>
      {assign && (
        <Dialog
          title="Assign an application role"
          onClose={() => setAssign(false)}
        >
          <ActionForm
            submitLabel="Assign role"
            onCancel={() => setAssign(false)}
            submit={async (data) => {
              await api(path, {
                method: "POST",
                body: {
                  role: text(data, "role"),
                  ...(subject === "user"
                    ? { user_id: number(data, "user_id") }
                    : { team_id: text(data, "team_id") }),
                },
              });
              setAssign(false);
              refresh();
              notify("Role assigned.");
            }}
          >
            <Field label="Subject type">
              <select
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              >
                <option value="user">Person</option>
                <option value="team">Team</option>
              </select>
            </Field>
            {subject === "user" ? (
              <Field label="User ID">
                <input name="user_id" type="number" min={1} required />
              </Field>
            ) : (
              <ReferenceSelect
                path="/api/v1/teams"
                name="team_id"
                label="Team"
                value={team}
                onChange={setTeam}
              />
            )}
            <Field label="Role">
              <select name="role">
                {["viewer", "developer", "approver", "operator"].map((role) => (
                  <option key={role}>{role}</option>
                ))}
              </select>
            </Field>
            <p className="form-hint">
              Roles grant platform actions. They do not grant external GitHub or
              data permissions.
            </p>
          </ActionForm>
        </Dialog>
      )}
      {remove && (
        <Dialog title="Remove role assignment?" onClose={() => setRemove(null)}>
          <p>
            This removes the {remove.role} assignment. Other direct or team
            assignments may still provide access.
          </p>
          <ActionForm
            submitLabel="Remove assignment"
            onCancel={() => setRemove(null)}
            submit={async () => {
              await api(`${path}/${remove.id}`, { method: "DELETE" });
              setRemove(null);
              refresh();
              notify("Role assignment removed.");
            }}
          >
            {null}
          </ActionForm>
        </Dialog>
      )}
    </section>
  );
}
