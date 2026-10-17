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
import type { Binding, Operation } from "../types";

type Source = {
  id: string;
  operation_id: string;
  requested_ref: string;
  repository_url: string;
  bundle_root: string;
  commit_sha: string | null;
  artifact_digest: string | null;
  captured_at: string | null;
  binding_snapshot: {
    binding_id: string;
    binding_version: number;
    bundle_target: string;
  };
};
type CIRun = {
  id: string;
  operation_id: string;
  commit_sha: string;
  run_attempt: number;
  status: string;
  conclusion: string | null;
  url: string;
  observed_at: string;
};

export function Sources({
  applicationId,
  canDevelop,
}: {
  applicationId: string;
  canDevelop: boolean;
}) {
  const path = `/api/v1/applications/${applicationId}`;
  const policy = useResource<{ enabled: boolean }>(`${path}/source-policy`);
  const [bindingId, setBindingId] = useState<string | null>(null);
  return (
    <>
      <div className="section-heading">
        <h3>GitHub source and CI</h3>
        <Badge tone="blue">GitHub reads</Badge>
      </div>
      <p>
        Capture an existing Python batch repository at one commit. CI results
        are recorded observations; deployment targets remain simulated.
      </p>
      <ErrorNotice error={policy.error} />
      {policy.loading && <Loading />}
      {policy.data && !policy.data.enabled && (
        <p>
          GitHub reads are disabled for this repository. An administrator must
          enable repository access before adoption.
        </p>
      )}
      <a className="text-button" href={`${path}/ci-onboarding`} download>
        Download CI workflow and onboarding instructions
      </a>
      {canDevelop && policy.data?.enabled && (
        <Paged<Binding>
          path={`${path}/bindings`}
          empty="No bindings available for adoption"
        >
          {(items) => (
            <ul className="attempt-list">
              {items.map((b) => (
                <li key={b.id}>
                  <strong>
                    {b.environment.name} / {b.bundle_target}
                  </strong>
                  <button
                    className="button small secondary"
                    disabled={!b.usable}
                    onClick={() => setBindingId(b.id)}
                  >
                    Adopt GitHub source
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Paged>
      )}
      <Paged<Source>
        path={`${path}/source-captures`}
        empty="No GitHub source captures"
        description="Refresh after the worker completes. Captures preserve the resolved commit even if a branch moves."
      >
        {(items) => (
          <ul className="attempt-list">
            {items.map((source) => (
              <SourceRow
                key={source.id}
                source={source}
                path={path}
                canDevelop={canDevelop}
                canRead={!!policy.data?.enabled}
              />
            ))}
          </ul>
        )}
      </Paged>
      <h3>Recorded CI observations</h3>
      <Paged<CIRun>
        path={`${path}/ci-runs`}
        empty="No CI observations"
        description="Refresh CI from a completed capture to record exact-commit results. A completed refresh can find no matching runs."
      >
        {(items) => (
          <ul className="attempt-list">
            {items.map((run) => (
              <li key={run.id}>
                <a href={run.url} target="_blank" rel="noreferrer">
                  CI {run.conclusion || run.status} · attempt {run.run_attempt}
                </a>
                <small className="break-word">Commit: {run.commit_sha}</small>
                <small>Observed {date(run.observed_at)}</small>
              </li>
            ))}
          </ul>
        )}
      </Paged>
      {bindingId && (
        <AdoptDialog
          path={path}
          bindingId={bindingId}
          onClose={() => setBindingId(null)}
        />
      )}
    </>
  );
}

function SourceRow({
  source,
  path,
  canDevelop,
  canRead,
}: {
  source: Source;
  path: string;
  canDevelop: boolean;
  canRead: boolean;
}) {
  const operation = useResource<Operation>(
    `/api/v1/operations/${source.operation_id}`,
  );
  const { refresh, notify, commandKey, completeCommand } = useData();
  return (
    <li>
      <strong>
        {source.requested_ref} / {source.binding_snapshot.bundle_target}
      </strong>
      <small>
        {source.repository_url} · {source.bundle_root}
      </small>
      <small className="break-word">
        Commit: {source.commit_sha || "Awaiting resolution"}
      </small>
      <ErrorNotice error={operation.error} />
      {operation.data && (
        <p>
          Capture {operation.data.status.replaceAll("_", " ")}
          {operation.data.diagnostic_code
            ? ` · ${operation.data.diagnostic_code.replaceAll("_", " ")}`
            : ""}
        </p>
      )}
      {source.artifact_digest && (
        <>
          <small>Captured {date(source.captured_at!)}</small>
          <a
            className="text-button"
            href={`/api/v1/artifacts/${source.artifact_digest}`}
            download
          >
            Download adopted bundle
          </a>
          {canDevelop && (
            <ActionForm
              submitLabel="Capture adopted revision"
              submit={async () => {
                await api(`${path}/revisions`, {
                  method: "POST",
                  body: {
                    source_capture_id: source.id,
                    binding_id: source.binding_snapshot.binding_id,
                    expected_binding_version:
                      source.binding_snapshot.binding_version,
                  },
                });
                notify(
                  "Immutable revision captured. Check it offline before approval.",
                );
                refresh();
              }}
            >
              <p>
                The saved source and binding configuration will be preserved.
              </p>
            </ActionForm>
          )}
          {canDevelop && canRead && (
            <ActionForm
              submitLabel="Refresh CI"
              submit={async () => {
                const scope = `ci:${source.id}`;
                await api(`/api/v1/source-captures/${source.id}/ci-refresh`, {
                  method: "POST",
                  body: {},
                  key: commandKey(scope),
                });
                completeCommand(scope);
                notify(
                  "CI refresh queued. Check Operations, then refresh this page.",
                );
                refresh();
              }}
            >
              <p>Read CI results for this captured commit.</p>
            </ActionForm>
          )}
        </>
      )}
    </li>
  );
}

function AdoptDialog({
  path,
  bindingId,
  onClose,
}: {
  path: string;
  bindingId: string;
  onClose: () => void;
}) {
  const binding = useResource<Binding>(`${path}/bindings/${bindingId}`);
  const { refresh, notify, commandKey, completeCommand } = useData();
  return (
    <Dialog
      title="Adopt GitHub source"
      description="The worker resolves the reference once and inspects the configured bundle root without executing its code."
      onClose={onClose}
    >
      <ErrorNotice error={binding.error} />
      {binding.loading && <Loading />}
      {binding.data?.usable && (
        <ActionForm
          submitLabel="Queue source capture"
          submit={async (form) => {
            const body = {
              binding_id: bindingId,
              expected_binding_version: binding.data!.version,
              ref: text(form, "ref"),
            };
            const scope = `source:${path}:${JSON.stringify(body)}`;
            await api(`${path}/source-captures`, {
              method: "POST",
              body,
              key: commandKey(scope),
            });
            completeCommand(scope);
            notify(
              "Source capture queued. Refresh after the worker completes.",
            );
            onClose();
            refresh();
          }}
        >
          <Field label="Branch, tag or commit">
            <input name="ref" defaultValue="main" required maxLength={200} />
          </Field>
        </ActionForm>
      )}
    </Dialog>
  );
}
