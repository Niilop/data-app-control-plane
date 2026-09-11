import { useState } from "react";
import {
  CheckCircle2,
  Download,
  FileArchive,
  FileJson,
  GitCommitHorizontal,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { api, downloadArtifact } from "../api";
import {
  ActionForm,
  AddButton,
  Badge,
  Dialog,
  Empty,
  ErrorNotice,
  Field,
  Loading,
  Paged,
  Status,
  date,
  label,
  text,
} from "../components";
import { ReferenceSelect } from "../ReferenceSelect";
import { useData, usePage, useResource } from "../state";
import type {
  Artifact,
  Binding,
  Revision,
  Template,
  Validation,
} from "../types";

const short = (digest: string) => digest.slice(0, 12);
const size = (bytes: number) => `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** Local generation is real work on this machine; deployment stays simulated. */
function LocalBadge() {
  return <Badge tone="blue">Local</Badge>;
}

export function Bundles({
  applicationId,
  canDevelop,
}: {
  applicationId: string;
  canDevelop: boolean;
}) {
  const [generate, setGenerate] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const templates = useResource<Template[]>("/api/v1/templates");
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Generated bundles</h2>
          <p>
            Deterministic local generation. The same template and inputs always
            produce the same archive digest.
          </p>
        </div>
        <div className="actions">
          <LocalBadge />
          {canDevelop && (
            <AddButton onClick={() => setGenerate(true)}>
              Generate bundle
            </AddButton>
          )}
        </div>
      </div>
      <ErrorNotice error={error || templates.error} />
      <TemplateSummary templates={templates.data} loading={templates.loading} />
      <Paged<Artifact>
        path={`/api/v1/applications/${applicationId}/artifacts`}
        empty="No artifacts yet"
        description="Generated bundles and validation reports appear here with their digests."
      >
        {(items) => (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Artifact</th>
                  <th>Digest</th>
                  <th>Size</th>
                  <th>Created</th>
                  <th>
                    <span className="sr-only">Download</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((artifact) => (
                  <tr key={artifact.id}>
                    <td>
                      <span className="cell-title">
                        {artifact.kind === "generated_bundle" ? (
                          <FileArchive size={17} />
                        ) : (
                          <FileJson size={17} />
                        )}
                        {label(artifact.kind)}
                      </span>
                      <small className="record-id">
                        {artifact.provenance.template_name
                          ? `${artifact.provenance.template_name} ${artifact.provenance.template_version}`
                          : `${artifact.provenance.scope ?? "offline"} report`}
                      </small>
                    </td>
                    <td>
                      <code>{short(artifact.digest)}…</code>
                    </td>
                    <td>{size(artifact.size_bytes)}</td>
                    <td>{date(artifact.created_at)}</td>
                    <td>
                      <button
                        className="text-button"
                        aria-label={`Download artifact ${artifact.digest}`}
                        onClick={async () => {
                          setError(null);
                          try {
                            await downloadArtifact(
                              artifact.digest,
                              `${short(artifact.digest)}.${
                                artifact.kind === "generated_bundle"
                                  ? "zip"
                                  : "json"
                              }`,
                            );
                          } catch (e) {
                            setError(e as Error);
                          }
                        }}
                      >
                        <Download size={14} />
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Paged>
      {generate && (
        <GenerateDialog
          applicationId={applicationId}
          templates={templates.data || []}
          onClose={() => setGenerate(false)}
        />
      )}
    </section>
  );
}

function TemplateSummary({
  templates,
  loading,
}: {
  templates: Template[] | null;
  loading: boolean;
}) {
  if (loading && !templates) return <Loading />;
  if (!templates?.length) return null;
  return (
    <div className="panel-body">
      <dl>
        {templates.map((template) => (
          <div key={`${template.name}@${template.version}`}>
            <dt>
              {template.title} {template.version}
            </dt>
            <dd>
              {template.summary}
              <small className="break-word">
                Template digest {short(template.content_digest)}… · produces{" "}
                {template.produces.length} files
              </small>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function GenerateDialog({
  applicationId,
  templates,
  onClose,
}: {
  applicationId: string;
  templates: Template[];
  onClose: () => void;
}) {
  const { refresh, notify, commandKey } = useData();
  const [binding, setBinding] = useState("");
  const active = templates.filter((template) => template.active);
  const template = active[0];
  return (
    <Dialog
      title="Generate a bundle"
      description="Generation runs locally with no network access. Slug and bundle target come from the application and its binding."
      onClose={onClose}
    >
      {!template ? (
        <Empty title="No approved template is available" />
      ) : (
        <ActionForm
          submitLabel="Generate bundle"
          onCancel={onClose}
          submit={async (data) => {
            const body = {
              template_name: template.name,
              template_version: template.version,
              binding_id: text(data, "binding_id"),
              package_name: text(data, "package_name"),
              synthetic_output_path: text(data, "synthetic_output_path"),
            };
            const result = await api<{ status: string }>(
              `/api/v1/applications/${applicationId}/generations`,
              {
                method: "POST",
                body,
                key: commandKey(
                  `${applicationId}:generate:${JSON.stringify(body)}`,
                ),
              },
            );
            notify(
              `Generation ${label(result.status)}. Refresh for the artifact.`,
            );
            onClose();
            refresh();
          }}
        >
          <Field
            label="Template"
            hint={`Content digest ${short(template.content_digest)}…`}
          >
            <input
              readOnly
              value={`${template.title} ${template.version}`}
              aria-label="Selected template"
            />
          </Field>
          <ReferenceSelect<Binding>
            path={`/api/v1/applications/${applicationId}/bindings`}
            name="binding_id"
            label="Environment binding"
            value={binding}
            onChange={setBinding}
            render={(item) =>
              `${item.bundle_target} · version ${item.version}${
                item.usable ? "" : " (unusable)"
              }`
            }
          />
          <Field
            label="Python package name"
            hint="Lowercase, for example customer_analytics."
          >
            <input
              name="package_name"
              required
              maxLength={40}
              pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*"
              placeholder="customer_analytics"
            />
          </Field>
          <Field
            label="Synthetic output location"
            hint="A relative .csv path inside the generated project."
          >
            <input
              name="synthetic_output_path"
              required
              maxLength={120}
              defaultValue="output/synthetic.csv"
            />
          </Field>
          <p className="form-hint">
            Row count and job timeout come from the binding configuration. No
            credentials, commands or URLs are accepted here.
          </p>
        </ActionForm>
      )}
    </Dialog>
  );
}

export function Revisions({
  applicationId,
  canDevelop,
}: {
  applicationId: string;
  canDevelop: boolean;
}) {
  const [capture, setCapture] = useState(false);
  const [selected, setSelected] = useState<Revision | null>(null);
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Revisions</h2>
          <p>
            Immutable snapshots of an artifact, its template, binding policy and
            configuration. Changing any input creates a new revision.
          </p>
        </div>
        <div className="actions">
          <Badge tone="blue">Simulated execution</Badge>
          {canDevelop && (
            <AddButton onClick={() => setCapture(true)}>
              Capture revision
            </AddButton>
          )}
        </div>
      </div>
      <Paged<Revision>
        path={`/api/v1/applications/${applicationId}/revisions`}
        empty="No revisions yet"
        description="Generate a bundle first, then capture it as a revision."
      >
        {(items) => (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Revision</th>
                  <th>Artifact</th>
                  <th>Target</th>
                  <th>Captured</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((revision) => (
                  <tr key={revision.id}>
                    <td>
                      <span className="cell-title">
                        <GitCommitHorizontal size={17} />
                        {label(revision.source_kind)}
                      </span>
                      <small className="record-id">{revision.id}</small>
                    </td>
                    <td>
                      <code>{short(revision.artifact_digest)}…</code>
                    </td>
                    <td>
                      <Badge>{revision.bundle_target}</Badge>
                    </td>
                    <td>{date(revision.created_at)}</td>
                    <td>
                      <button
                        className="text-button"
                        aria-label={`View revision ${revision.id}`}
                        onClick={() => setSelected(revision)}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Paged>
      {capture && (
        <CaptureDialog
          applicationId={applicationId}
          onClose={() => setCapture(false)}
        />
      )}
      {selected && (
        <RevisionDetail
          key={selected.id}
          revision={selected}
          canDevelop={canDevelop}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function CaptureDialog({
  applicationId,
  onClose,
}: {
  applicationId: string;
  onClose: () => void;
}) {
  const { refresh, notify } = useData();
  const [binding, setBinding] = useState("");
  const [digest, setDigest] = useState("");
  const [override, setOverride] = useState(false);
  const bundles = usePage<Artifact>(
    `/api/v1/applications/${applicationId}/artifacts`,
  );
  const available = (bundles.data?.items || []).filter(
    (artifact) => artifact.kind === "generated_bundle",
  );
  return (
    <Dialog
      title="Capture a revision"
      description="The captured snapshot cannot be edited afterwards."
      onClose={onClose}
    >
      <ErrorNotice error={bundles.error} />
      {bundles.loading && !bundles.data ? (
        <Loading />
      ) : !available.length ? (
        <Empty title="Generate a bundle first">
          A revision records an artifact that already exists.
        </Empty>
      ) : (
        <ActionForm
          submitLabel="Capture revision"
          onCancel={onClose}
          submit={async (data) => {
            await api(`/api/v1/applications/${applicationId}/revisions`, {
              method: "POST",
              body: {
                artifact_digest: text(data, "artifact_digest"),
                binding_id: text(data, "binding_id"),
                ...(override
                  ? {
                      config: {
                        schema_version: 1,
                        synthetic_row_count: Number(
                          data.get("synthetic_row_count"),
                        ),
                        max_runtime_seconds: Number(
                          data.get("max_runtime_seconds"),
                        ),
                      },
                    }
                  : {}),
              },
            });
            notify("Revision captured.");
            onClose();
            refresh();
          }}
        >
          <Field label="Generated bundle">
            <select
              name="artifact_digest"
              required
              value={digest}
              onChange={(event) => setDigest(event.target.value)}
            >
              <option value="">Select an artifact</option>
              {available.map((artifact) => (
                <option key={artifact.id} value={artifact.digest}>
                  {short(artifact.digest)}… · {date(artifact.created_at)}
                </option>
              ))}
            </select>
          </Field>
          <ReferenceSelect<Binding>
            path={`/api/v1/applications/${applicationId}/bindings`}
            name="binding_id"
            label="Environment binding"
            value={binding}
            onChange={setBinding}
            render={(item) =>
              `${item.bundle_target} · version ${item.version}${
                item.usable ? "" : " (unusable)"
              }`
            }
          />
          <Field label="Configuration">
            <select
              value={override ? "override" : "binding"}
              onChange={(event) =>
                setOverride(event.target.value === "override")
              }
            >
              <option value="binding">Use the binding configuration</option>
              <option value="override">Record different values</option>
            </select>
          </Field>
          {override && (
            <div className="form-grid">
              <Field label="Synthetic rows" hint="1–10,000.">
                <input
                  name="synthetic_row_count"
                  type="number"
                  min={1}
                  max={10000}
                  step={1}
                  defaultValue={100}
                  required
                />
              </Field>
              <Field label="Maximum runtime (seconds)" hint="1–3,600.">
                <input
                  name="max_runtime_seconds"
                  type="number"
                  min={1}
                  max={3600}
                  step={1}
                  defaultValue={300}
                  required
                />
              </Field>
            </div>
          )}
        </ActionForm>
      )}
    </Dialog>
  );
}

function RevisionDetail({
  revision,
  canDevelop,
  onClose,
}: {
  revision: Revision;
  canDevelop: boolean;
  onClose: () => void;
}) {
  const { refresh, notify, commandKey } = useData();
  const [error, setError] = useState<Error | null>(null);
  const environment = revision.binding_snapshot.environment || {};
  return (
    <Dialog
      title="Revision snapshot"
      description="Source, template, binding policy and configuration as captured. These values never change."
      onClose={onClose}
    >
      <ErrorNotice error={error} />
      <div className="operation-status">
        <Badge tone="blue">Simulated execution</Badge>
        <Badge>{revision.bundle_target}</Badge>
        <button
          className="text-button"
          onClick={async () => {
            setError(null);
            try {
              await downloadArtifact(
                revision.artifact_digest,
                `${short(revision.artifact_digest)}.zip`,
              );
            } catch (e) {
              setError(e as Error);
            }
          }}
        >
          <Download size={14} />
          Download bundle
        </button>
      </div>
      <dl>
        <dt>Revision ID</dt>
        <dd className="break-word">{revision.id}</dd>
        <dt>Source</dt>
        <dd>{label(revision.source_kind)}</dd>
        <dt>Artifact digest</dt>
        <dd className="break-word">
          <code>{revision.artifact_digest}</code>
        </dd>
        <dt>Approval scope digest</dt>
        <dd className="break-word">
          <code>{revision.scope_digest}</code>
        </dd>
        <dt>Configuration digest</dt>
        <dd className="break-word">
          <code>{revision.config_digest}</code>
        </dd>
        <dt>Binding version</dt>
        <dd>{revision.binding_version}</dd>
        <dt>Workspace reference</dt>
        <dd className="break-word">{environment.workspace_ref}</dd>
        <dt>Self-approval allowed</dt>
        <dd>{environment.allow_self_approval ? "Yes" : "No"}</dd>
        <dt>Synthetic rows</dt>
        <dd>{revision.config_snapshot.synthetic_row_count}</dd>
        <dt>Maximum runtime</dt>
        <dd>{revision.config_snapshot.max_runtime_seconds} seconds</dd>
        <dt>Captured</dt>
        <dd>{date(revision.created_at)}</dd>
      </dl>
      <h3>Offline validation</h3>
      <p className="muted">
        These checks read the captured archive on this machine. They never
        contact a workspace and are not workspace validation.
      </p>
      <Paged<Validation>
        path={`/api/v1/revisions/${revision.id}/validations`}
        empty="No validation has run yet"
      >
        {(items) => (
          <ul className="attempt-list">
            {items.map((validation) => (
              <li key={validation.id}>
                <div>
                  <strong>
                    {validation.result === "passed" ? (
                      <CheckCircle2 size={16} />
                    ) : (
                      <XCircle size={16} />
                    )}{" "}
                    Offline checks
                  </strong>
                  <Status value={validation.result || "queued"} />
                </div>
                <small>
                  {validation.validator} {validation.validator_version} ·{" "}
                  {date(validation.observed_at)}
                </small>
                <p>
                  {validation.check_summary.passed ?? 0} of{" "}
                  {validation.check_summary.total ?? 0} checks passed
                  {validation.check_summary.failed?.length
                    ? `: ${validation.check_summary.failed.map(label).join(", ")} failed`
                    : ""}
                  .
                </p>
                <small className="break-word">
                  Offline scope only — not evidence of workspace validity.
                </small>
              </li>
            ))}
          </ul>
        )}
      </Paged>
      {canDevelop && (
        <div className="form-section">
          <h3>Run offline validation</h3>
          <p className="muted">
            <ShieldAlert size={14} /> Offline scope is the only supported scope.
            A passing report does not authorize deployment.
          </p>
          <ActionForm
            submitLabel="Run offline checks"
            submit={async () => {
              const body = { scope: "offline" };
              const result = await api<{ status: string }>(
                `/api/v1/revisions/${revision.id}/validations`,
                {
                  method: "POST",
                  body,
                  key: commandKey(`${revision.id}:validate:offline`),
                },
              );
              notify(`Offline validation ${label(result.status)}.`);
              refresh();
            }}
          >
            {null}
          </ActionForm>
        </div>
      )}
    </Dialog>
  );
}
