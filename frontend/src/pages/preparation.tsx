import { useState } from "react";
import { api } from "../api";
import {
  ActionForm,
  Badge,
  Dialog,
  ErrorNotice,
  Field,
  Loading,
  Paged,
  date,
  text,
} from "../components";
import { useData, useResource } from "../state";
import type { Binding } from "../types";

type Snapshot = {
  binding_id: string;
  binding_version: number;
  bundle_target: string;
  environment_version: number;
  workspace_ref: string;
  config: Binding["config"];
};
type Generation = {
  id: string;
  operation_id: string;
  template_id: string;
  artifact_digest: string | null;
  binding_snapshot: Snapshot;
  parameters: { package_name: string };
};
type Revision = {
  id: string;
  artifact_digest: string;
  template_id: string;
  template_digest: string;
  config_digest: string;
  binding_snapshot: Snapshot;
  created_at: string;
};
type Validation = {
  id: string;
  result: string;
  report_digest: string;
  observed_at: string;
  validator_version: string;
};
type Template = { id: string; content_digest: string; active: boolean };

export function Preparation({
  applicationId,
  canDevelop,
}: {
  applicationId: string;
  canDevelop: boolean;
}) {
  const [binding, setBinding] = useState<Binding | null>(null);
  const [capture, setCapture] = useState<Generation | null>(null);
  const [selected, setSelected] = useState<Revision | null>(null);
  const { refresh, notify, commandKey } = useData();
  const templates = useResource<Template[]>("/api/v1/templates");
  const path = `/api/v1/applications/${applicationId}`;
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Prepare a revision</h2>
          <p>
            Generate a synthetic Python batch, capture its configuration, and
            check it offline.
          </p>
        </div>
        <Badge tone="blue">Offline</Badge>
      </div>
      <div className="panel-body preparation-content">
        <p>
          Offline checks do not establish workspace validity. Environment
          targets remain simulated.
        </p>
        <ErrorNotice error={templates.error} />
        {templates.loading && <Loading />}
        {templates.data?.map((t) => (
          <p key={t.id}>
            {t.id} · {t.active ? "Available" : "Inactive"}
            <small className="record-id break-word">
              Template SHA-256: {t.content_digest}
            </small>
          </p>
        ))}
        {canDevelop && (
          <>
            <h3>Choose an environment binding</h3>
            <Paged<Binding>
              path={`${path}/bindings`}
              empty="No environment bindings"
              description="An administrator must configure a binding before generation."
            >
              {(items) => (
                <ul className="attempt-list">
                  {items.map((b) => (
                    <li key={b.id}>
                      <div>
                        <strong>
                          {b.environment.name} / {b.bundle_target}
                        </strong>
                        <button
                          className="button small secondary"
                          disabled={
                            !b.usable ||
                            templates.loading ||
                            !templates.data?.some((t) => t.active)
                          }
                          onClick={() => setBinding(b)}
                        >
                          Generate bundle
                        </button>
                      </div>
                      <small>
                        Binding version {b.version} ·{" "}
                        {b.config.synthetic_row_count} synthetic rows
                      </small>
                    </li>
                  ))}
                </ul>
              )}
            </Paged>
          </>
        )}
        <h3>Generations</h3>
        <Paged<Generation>
          path={`${path}/generations`}
          empty="No generations yet"
          description="Refresh after the worker completes. Progress and recovery are in Operations."
        >
          {(items) => (
            <ul className="attempt-list">
              {items.map((g) => (
                <li key={g.id}>
                  <strong>
                    {g.parameters.package_name} /{" "}
                    {g.binding_snapshot.bundle_target}
                  </strong>
                  <small className="record-id">
                    Operation: {g.operation_id}
                  </small>
                  {g.artifact_digest ? (
                    <>
                      <ArtifactLink
                        digest={g.artifact_digest}
                        label="Download bundle"
                      />
                      {canDevelop && (
                        <button
                          className="button small secondary"
                          onClick={() => setCapture(g)}
                        >
                          Capture revision
                        </button>
                      )}
                    </>
                  ) : (
                    <p>
                      Artifact pending. Check Operations for status and
                      diagnostics.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Paged>
        <h3>Immutable revisions</h3>
        <Paged<Revision>
          path={`${path}/revisions`}
          empty="No revisions captured"
        >
          {(items) => (
            <ul className="attempt-list">
              {items.map((r) => (
                <li key={r.id}>
                  <strong>
                    {r.binding_snapshot.bundle_target} · {date(r.created_at)}
                  </strong>
                  <small className="record-id break-word">{r.id}</small>
                  <button
                    className="button small secondary"
                    onClick={() => setSelected(r)}
                  >
                    View revision
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Paged>
      </div>
      {binding && (
        <GenerationDialog
          bindingId={binding.id}
          path={path}
          onClose={() => setBinding(null)}
        />
      )}
      {capture && (
        <Dialog
          title="Capture immutable revision"
          description="The saved artifact and binding configuration cannot be edited."
          onClose={() => setCapture(null)}
        >
          <SnapshotDetails snapshot={capture.binding_snapshot} />
          <ActionForm
            submitLabel="Capture revision"
            submit={async () => {
              await api(`${path}/revisions`, {
                method: "POST",
                body: {
                  generation_id: capture.id,
                  binding_id: capture.binding_snapshot.binding_id,
                  expected_binding_version:
                    capture.binding_snapshot.binding_version,
                },
              });
              notify("Revision captured.");
              refresh();
              setCapture(null);
            }}
          >
            <p>
              Binding changes require a new generation. If a response is lost,
              inspect the revision list before submitting again.
            </p>
          </ActionForm>
        </Dialog>
      )}
      {selected && (
        <Dialog
          title="Immutable revision"
          description="Source and configuration are preserved exactly as captured."
          onClose={() => setSelected(null)}
        >
          <small className="record-id break-word">{selected.id}</small>
          <SnapshotDetails snapshot={selected.binding_snapshot} />
          <p>Template: {selected.template_id}</p>
          <p className="break-word">Config SHA-256: {selected.config_digest}</p>
          <ArtifactLink
            digest={selected.artifact_digest}
            label="Download captured bundle"
          />
          <h3>Offline validation reports</h3>
          <Paged<Validation>
            path={`/api/v1/revisions/${selected.id}/validations`}
            empty="No offline validation reports"
          >
            {(items) => (
              <ul className="attempt-list">
                {items.map((v) => (
                  <li key={v.id}>
                    <strong>Offline checks {v.result}</strong>
                    <small>
                      {v.validator_version} · {date(v.observed_at)}
                    </small>
                    <ArtifactLink
                      digest={v.report_digest}
                      label="Download offline report"
                    />
                  </li>
                ))}
              </ul>
            )}
          </Paged>
          {canDevelop && (
            <ActionForm
              submitLabel="Validate offline"
              submit={async () => {
                const target = `/api/v1/revisions/${selected.id}/validations`;
                await api(target, {
                  method: "POST",
                  body: { scope: "offline" },
                  key: commandKey(target),
                });
                notify(
                  "Offline validation queued. Refresh to view its report; progress is in Operations.",
                );
                refresh();
              }}
            >
              <p>
                Checks approved content and static syntax. Does not execute code
                or contact a workspace.
              </p>
            </ActionForm>
          )}
        </Dialog>
      )}
    </section>
  );
}
function GenerationDialog({
  bindingId,
  path,
  onClose,
}: {
  bindingId: string;
  path: string;
  onClose: () => void;
}) {
  const resource = useResource<Binding>(`${path}/bindings/${bindingId}`);
  const { commandKey, notify, refresh } = useData();
  const binding = resource.data;
  return (
    <Dialog
      title="Generate bundle"
      description="Uses the approved Python batch template and this binding’s configuration."
      onClose={onClose}
    >
      <ErrorNotice error={resource.error} />
      {resource.loading ? (
        <Loading />
      ) : (
        binding && (
          <ActionForm
            submitLabel="Queue generation"
            submit={async (data) => {
              const body = {
                template_id: "python-batch:1.0.0",
                binding_id: binding.id,
                expected_binding_version: binding.version,
                parameters: { package_name: text(data, "package_name") },
              };
              await api(`${path}/generations`, {
                method: "POST",
                body,
                key: commandKey(`${path}:generate:${JSON.stringify(body)}`),
              });
              notify(
                "Generation queued. Refresh to see the artifact; progress is in Operations.",
              );
              refresh();
              onClose();
            }}
          >
            <p>
              {binding.environment.name} / {binding.bundle_target} · Binding
              version {binding.version}
            </p>
            <Field
              label="Python package name"
              hint="Start with batch_, followed by a lowercase letter; then lowercase letters, digits or underscores."
            >
              <input
                name="package_name"
                defaultValue="batch_app"
                required
                pattern="batch_[a-z][a-z0-9_]{0,39}"
                maxLength={46}
              />
            </Field>
          </ActionForm>
        )
      )}
    </Dialog>
  );
}
function SnapshotDetails({ snapshot }: { snapshot: Snapshot }) {
  return (
    <dl>
      <dt>Target</dt>
      <dd>{snapshot.bundle_target} (simulated)</dd>
      <dt>Workspace reference</dt>
      <dd>{snapshot.workspace_ref}</dd>
      <dt>Binding / environment version</dt>
      <dd>
        {snapshot.binding_version} / {snapshot.environment_version}
      </dd>
      <dt>Synthetic rows</dt>
      <dd>{snapshot.config.synthetic_row_count}</dd>
      <dt>Maximum runtime</dt>
      <dd>{snapshot.config.max_runtime_seconds} seconds</dd>
    </dl>
  );
}
function ArtifactLink({ digest, label }: { digest: string; label: string }) {
  return (
    <div className="artifact-download">
      <a className="text-button" href={`/api/v1/artifacts/${digest}`} download>
        {label}
      </a>
      <small className="record-id break-word">SHA-256: {digest}</small>
    </div>
  );
}
