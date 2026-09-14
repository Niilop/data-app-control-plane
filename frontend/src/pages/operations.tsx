import { useState } from "react";
import { Activity, ArrowRight } from "lucide-react";
import { api } from "../api";
import {
  ActionForm,
  Badge,
  date,
  Dialog,
  ErrorNotice,
  Field,
  label,
  Loading,
  Paged,
  Status,
  text,
} from "../components";
import { useData, useResource } from "../state";
import type { Attempt, Operation } from "../types";

export function Operations({
  applicationId,
  canOperate,
}: {
  applicationId: string;
  canOperate: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Operations</h2>
          <p>Execution progress, attempts and recovery history.</p>
        </div>
        <Badge tone="blue">Local work</Badge>
      </div>
      <Paged<Operation>
        path={`/api/v1/applications/${applicationId}/operations`}
        empty="No operations yet"
        description="Queued work will appear here with its status and latest observation."
      >
        {(items) => (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Last observed</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((operation) => (
                  <tr key={operation.id}>
                    <td>
                      <span className="cell-title">
                        <Activity size={17} />
                        {label(operation.kind)}
                      </span>
                      <small className="record-id">{operation.id}</small>
                    </td>
                    <td>
                      <Status value={operation.status} />
                      <Badge tone="blue">
                        {label(operation.execution_mode)}
                      </Badge>
                    </td>
                    <td>
                      {operation.attempt_count} / {operation.max_attempts}
                    </td>
                    <td>{date(operation.observed_at)}</td>
                    <td>
                      <button
                        className="text-button"
                        aria-label={`View operation ${operation.id}`}
                        onClick={() => setSelected(operation.id)}
                      >
                        Details
                        <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Paged>
      {selected && (
        <OperationDetail
          key={selected}
          id={selected}
          canOperate={canOperate}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}
function OperationDetail({
  id,
  canOperate,
  onClose,
}: {
  id: string;
  canOperate: boolean;
  onClose: () => void;
}) {
  const resource = useResource<Operation>(`/api/v1/operations/${id}`);
  const { refresh, notify, commandKey } = useData();
  const operation = resource.data;
  const action =
    operation?.status === "needs_attention"
      ? "reconcile"
      : ["failed", "cancelled"].includes(operation?.status || "")
        ? "retry"
        : ["queued", "running", "retry_wait", "reconciling"].includes(
              operation?.status || "",
            )
          ? "cancel"
          : null;
  return (
    <Dialog
      title="Operation details"
      description="Observations reflect the last recorded worker state."
      onClose={onClose}
    >
      <ErrorNotice error={resource.error} />
      {!operation ? (
        resource.loading ? (
          <Loading />
        ) : null
      ) : (
        <>
          <div className="operation-status">
            <Status value={operation.status} />
            <Badge tone="blue">{label(operation.execution_mode)}</Badge>
            <Badge tone="blue">Local work</Badge>
            <button className="text-button" onClick={refresh}>
              Refresh operation
            </button>
          </div>
          <dl>
            <dt>Operation ID</dt>
            <dd className="break-word">{operation.id}</dd>
            <dt>Requested by</dt>
            <dd>User #{operation.requested_by}</dd>
            <dt>Attempts</dt>
            <dd>
              {operation.attempt_count} / {operation.max_attempts}
            </dd>
            <dt>Last observed</dt>
            <dd>{date(operation.observed_at)}</dd>
            <dt>Heartbeat</dt>
            <dd>{date(operation.heartbeat_at)}</dd>
            <dt>Lease expires</dt>
            <dd>{date(operation.lease_expires_at)}</dd>
            {operation.retry_of && (
              <>
                <dt>Retry of</dt>
                <dd className="break-word">{operation.retry_of}</dd>
              </>
            )}
          </dl>
          {operation.diagnostic_code && (
            <div className="alert">{label(operation.diagnostic_code)}</div>
          )}
          {operation.cancel_requested && (
            <div className="alert">
              Cancellation requested. Running or uncertain work requires a
              worker observation.
            </div>
          )}
          <h3>Attempt history</h3>
          <Paged<Attempt>
            path={`/api/v1/operations/${id}/attempts`}
            empty="No attempts recorded"
          >
            {(items) => (
              <ul className="attempt-list">
                {items.map((attempt) => (
                  <li key={attempt.id}>
                    <div>
                      <strong>{label(attempt.phase)}</strong>
                      <Status value={attempt.outcome} />
                    </div>
                    <small>
                      {date(attempt.created_at)} → {date(attempt.finished_at)}
                    </small>
                    {attempt.diagnostic_code && (
                      <p>{label(attempt.diagnostic_code)}</p>
                    )}
                    <small className="break-word">
                      Correlation: {attempt.correlation_id}
                    </small>
                  </li>
                ))}
              </ul>
            )}
          </Paged>
          {canOperate && action && (
            <div className="form-section">
              <h3>
                {action === "cancel"
                  ? "Request cancellation"
                  : action === "retry"
                    ? "Retry operation"
                    : "Reconcile outcome"}
              </h3>
              <p className="muted">
                {action === "cancel"
                  ? "Running work is cancelled only when the worker observes your request."
                  : action === "retry"
                    ? "Create a new linked operation after current policy checks."
                    : "Request another observation. This does not force a result or release uncertain work."}
              </p>
              <ActionForm
                key={action}
                submitLabel={
                  action === "cancel"
                    ? "Request cancellation"
                    : action === "retry"
                      ? "Retry operation"
                      : "Request reconciliation"
                }
                submit={async (data) => {
                  const body =
                    action === "reconcile"
                      ? { evidence: text(data, "evidence") }
                      : {};
                  const scope = `${id}:${action}:${JSON.stringify(body)}`;
                  const result = await api<{
                    operation_id: string;
                    status: string;
                  }>(`/api/v1/operations/${id}/${action}`, {
                    method: "POST",
                    body,
                    key: commandKey(scope),
                  });
                  // Workspace memory preserves keys across dialog reopen and transport retries.
                  notify(`Operation ${label(result.status)}.`);
                  refresh();
                  onClose();
                }}
              >
                {action === "reconcile" && (
                  <Field
                    label="Reason to reconcile"
                    hint="Describe the observation to check; do not paste secrets."
                  >
                    <textarea
                      name="evidence"
                      required
                      maxLength={500}
                      rows={3}
                    />
                  </Field>
                )}
              </ActionForm>
            </div>
          )}
        </>
      )}
    </Dialog>
  );
}
