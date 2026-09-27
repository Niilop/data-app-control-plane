import { Badge, Paged, date } from "../components";
import type { Operation } from "../types";
import { RunHistory } from "./job-runs";

type Revision = {
  id: string;
  created_at: string;
  artifact_digest: string;
  binding_snapshot: { bundle_target: string };
};
type Approval = {
  id: string;
  decision: string;
  created_at: string;
  scope_digest: string;
};
type Deployment = {
  id: string;
  revision_id: string;
  approval_id: string;
  status: string;
  last_observed_at: string | null;
};

export function ApplicationDashboard({
  applicationId,
}: {
  applicationId: string;
}) {
  const path = `/api/v1/applications/${applicationId}`;
  return (
    <section className="panel full-width">
      <div className="panel-body preparation-content">
        <h2>Recorded application activity</h2>
        <p>
          <Badge tone="blue">Simulated</Badge> Recorded database state. Refresh
          to see worker observations. Run outcomes are separate from deployment
          outcomes.
        </p>
        <h3>Revisions and approval evidence</h3>
        <Paged<Revision> path={`${path}/revisions`} empty="No revisions yet">
          {(items) => (
            <ul className="attempt-list">
              {items.map((row) => (
                <li key={row.id}>
                  <strong className="break-word">Revision: {row.id}</strong>
                  <p>
                    Target: {row.binding_snapshot.bundle_target} · Captured:{" "}
                    {date(row.created_at)}
                  </p>
                  <small className="record-id break-word">
                    Source SHA-256: {row.artifact_digest}
                  </small>
                  <details>
                    <summary>Approval history for this revision</summary>
                    <Paged<Approval>
                      path={`/api/v1/revisions/${row.id}/approvals`}
                      empty="No approval decisions"
                    >
                      {(approvals) => (
                        <ul className="attempt-list">
                          {approvals.map((approval) => (
                            <li key={approval.id}>
                              <strong>{approval.decision}</strong> ·{" "}
                              {date(approval.created_at)}
                              <small className="record-id break-word">
                                Approval: {approval.id}
                              </small>
                              <small className="record-id break-word">
                                Scope SHA-256: {approval.scope_digest}
                              </small>
                            </li>
                          ))}
                        </ul>
                      )}
                    </Paged>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </Paged>
        <h3>Deployment observations</h3>
        <Paged<Deployment>
          path={`${path}/deployments`}
          empty="No deployments yet"
        >
          {(items) => (
            <ul className="attempt-list">
              {items.map((row) => (
                <li key={row.id}>
                  <strong>{row.status} · Simulated</strong>
                  <small className="record-id break-word">
                    Deployment: {row.id}
                  </small>
                  <small className="record-id break-word">
                    Revision: {row.revision_id}
                  </small>
                  <small className="record-id break-word">
                    Approval: {row.approval_id}
                  </small>
                  <p>
                    Last observed:{" "}
                    {row.last_observed_at
                      ? date(row.last_observed_at)
                      : "Pending"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Paged>
        <h3>Job results</h3>
        <RunHistory path={`${path}/runs`} />
        <h3>Operation history</h3>
        <Paged<Operation> path={`${path}/operations`} empty="No operations yet">
          {(items) => (
            <ul className="attempt-list">
              {items.map((row) => (
                <li key={row.id}>
                  <strong>
                    {row.kind.replaceAll("_", " ")} · {row.status} ·{" "}
                    {row.execution_mode}
                  </strong>
                  <small className="record-id break-word">
                    Operation: {row.id}
                  </small>
                  <p>
                    Last observed:{" "}
                    {row.observed_at ? date(row.observed_at) : "Pending"}
                  </p>
                  {row.diagnostic_code && (
                    <p>{row.diagnostic_code.replaceAll("_", " ")}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Paged>
      </div>
    </section>
  );
}
