import { useState } from "react";
import { api } from "../api";
import {
  ActionForm,
  Badge,
  ErrorNotice,
  Field,
  Loading,
  Paged,
  date,
  text,
} from "../components";
import { useData, useResource } from "../state";
import type { Binding } from "../types";
import { RunControls, RunHistory } from "./job-runs";

type Approval = {
  id: string;
  decision: string;
  approver_id: number;
  scope_digest: string;
  reason: string;
  self_approval_acknowledged: boolean;
  created_at: string;
};
type Scope = { scope_digest: string; scope: Record<string, unknown> };
type Deployment = {
  id: string;
  binding_id: string;
  revision_id: string;
  approval_id: string;
  operation_id: string;
  status: string;
  execution_mode: "simulated";
  scenario: string;
  last_observed_at: string | null;
  resources: {
    resource_key: string;
    reference: string;
    status: string;
    execution_mode: string;
  }[];
};

export function ApprovalControls({
  revisionId,
  bindingId,
  validationId,
  canApprove,
  canDeploy,
}: {
  revisionId: string;
  bindingId: string;
  validationId: string;
  canApprove: boolean;
  canDeploy: boolean;
}) {
  const scope = useResource<Scope>(
    `/api/v1/revisions/${revisionId}/approval-scope?validation_id=${validationId}`,
  );
  const { notify, refresh } = useData();
  return (
    <section>
      <h3>Approve exact scope</h3>
      <p>
        Simulated deployment only. Offline validation does not establish
        workspace validity.
      </p>
      <ErrorNotice error={scope.error} />
      {scope.loading ? (
        <Loading />
      ) : (
        scope.data && (
          <>
            <p className="break-word">
              Scope SHA-256: {scope.data.scope_digest}
            </p>
            <details>
              <summary>
                Review source, template, configuration, target, policy and
                report
              </summary>
              <pre className="scope-evidence">
                {JSON.stringify(scope.data.scope, null, 2)}
              </pre>
            </details>
            {canApprove && (
              <ActionForm
                submitLabel="Record decision"
                submit={async (form) => {
                  await api(`/api/v1/revisions/${revisionId}/approvals`, {
                    method: "POST",
                    body: {
                      validation_id: validationId,
                      scope_digest: scope.data!.scope_digest,
                      decision: text(form, "decision"),
                      reason: text(form, "reason"),
                      acknowledge_local_self_approval:
                        form.get("self_approval") === "on",
                    },
                  });
                  notify("Approval decision recorded for this exact scope.");
                  refresh();
                }}
              >
                <Field label="Decision">
                  <select name="decision">
                    <option value="approved">Approve</option>
                    <option value="rejected">Reject</option>
                  </select>
                </Field>
                <Field label="Decision reason">
                  <input name="reason" required maxLength={500} />
                </Field>
                <label>
                  <input type="checkbox" name="self_approval" /> I explicitly
                  acknowledge local self-approval when permitted by this
                  binding’s policy.
                </label>
                <p>
                  Self-approval is audited and requires an enabled environment
                  policy. If a response is lost, inspect decisions before
                  recording another.
                </p>
              </ActionForm>
            )}
          </>
        )
      )}
      <p className="record-id">Binding: {bindingId}</p>
      {canDeploy && (
        <p>Choose an approved decision below to submit the simulation.</p>
      )}
    </section>
  );
}

export function RevisionApprovals({
  revisionId,
  bindingId,
  applicationId,
  canDeploy,
}: {
  revisionId: string;
  bindingId: string;
  applicationId: string;
  canDeploy: boolean;
}) {
  const { notify, refresh, commandKey } = useData();
  return (
    <>
      <h3>Approval decisions</h3>
      <Paged<Approval>
        path={`/api/v1/revisions/${revisionId}/approvals`}
        empty="No approval decisions"
      >
        {(items) => (
          <ul className="attempt-list">
            {items.map((a) => (
              <li key={a.id}>
                <strong>
                  {a.decision} · User #{a.approver_id}
                </strong>
                <small>
                  {date(a.created_at)} ·{" "}
                  {a.self_approval_acknowledged
                    ? "Local self-approval acknowledged"
                    : "Independent approval policy"}
                </small>
                <p>{a.reason}</p>
                <small className="record-id break-word">
                  Scope: {a.scope_digest}
                </small>
                {canDeploy && a.decision === "approved" && (
                  <ActionForm
                    submitLabel="Submit simulated deployment"
                    submit={async (form) => {
                      const path = `/api/v1/applications/${applicationId}/deployments`;
                      const body = {
                        revision_id: revisionId,
                        binding_id: bindingId,
                        approval_id: a.id,
                        execution_mode: "simulated",
                        scenario: text(form, "scenario"),
                      };
                      const result = await api<{ operation_id: string }>(path, {
                        method: "POST",
                        body,
                        key: commandKey(`${path}:${JSON.stringify(body)}`),
                      });
                      notify(
                        `Simulated deployment queued. Operation: ${result.operation_id}`,
                      );
                      refresh();
                    }}
                  >
                    <Field label="Simulation scenario">
                      <select name="scenario">
                        <option value="success">Simulated success</option>
                        <option value="partial_failure">
                          Simulated partial failure
                        </option>
                      </select>
                    </Field>
                    <p>
                      Submission rechecks current roles, approver and binding
                      policy. No provider resources are created.
                    </p>
                  </ActionForm>
                )}
              </li>
            ))}
          </ul>
        )}
      </Paged>
    </>
  );
}

function DeploymentDetails({ row }: { row: Deployment }) {
  return (
    <div>
      <strong>
        {row.status} · <Badge tone="blue">Simulated</Badge>
      </strong>
      <small className="record-id break-word">Deployment: {row.id}</small>
      <small className="record-id break-word">
        Revision: {row.revision_id}
      </small>
      <small className="record-id break-word">
        Approval: {row.approval_id}
      </small>
      <small className="record-id break-word">Binding: {row.binding_id}</small>
      <small className="record-id break-word">
        Operation: {row.operation_id}
      </small>
      <p>
        Scenario: {row.scenario} · Last observed:{" "}
        {row.last_observed_at ? date(row.last_observed_at) : "Pending"}
      </p>
      {row.resources.map((r) => (
        <p key={r.resource_key} className="break-word">
          {r.resource_key}: {r.status} · {r.reference} ({r.execution_mode})
        </p>
      ))}
    </div>
  );
}
function LastSuccess({ path }: { path: string }) {
  const row = useResource<Deployment | null>(path);
  return (
    <>
      <ErrorNotice error={row.error} />
      {row.loading ? (
        <Loading />
      ) : row.data ? (
        <DeploymentDetails row={row.data} />
      ) : (
        <p>No successful simulated deployment for this binding.</p>
      )}
    </>
  );
}
export function Deployments({
  applicationId,
  canOperate,
}: {
  applicationId: string;
  canOperate: boolean;
}) {
  const [binding, setBinding] = useState("");
  const path = `/api/v1/applications/${applicationId}`;
  return (
    <section className="panel">
      <div className="panel-body preparation-content">
        <h2>Simulated deployments</h2>
        <p>
          These records describe local simulation. Deployment success does not
          imply a data job ran. Refresh for worker observations; recovery is in
          Operations.
        </p>
        <h3>Last successful deployment</h3>
        <Paged<Binding> path={`${path}/bindings`} empty="No bindings">
          {(items) => (
            <Field label="Last-success binding">
              <select
                value={binding}
                onChange={(event) => setBinding(event.target.value)}
              >
                <option value="">Choose a binding</option>
                {items.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.environment.name} / {b.bundle_target}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </Paged>
        {binding && (
          <LastSuccess path={`${path}/bindings/${binding}/last-success`} />
        )}
        <h3>Deployment history</h3>
        <Paged<Deployment>
          path={`${path}/deployments`}
          empty="No deployments yet"
          description="Prepare, validate and approve an exact revision to submit a simulation."
        >
          {(items) => (
            <ul className="attempt-list">
              {items.map((row) => (
                <li key={row.id}>
                  <DeploymentDetails row={row} />
                  {canOperate && row.status === "succeeded" && (
                    <RunControls deploymentId={row.id} />
                  )}
                  <details>
                    <summary>Job run history</summary>
                    <RunHistory path={`/api/v1/deployments/${row.id}/runs`} />
                  </details>
                </li>
              ))}
            </ul>
          )}
        </Paged>
      </div>
    </section>
  );
}
