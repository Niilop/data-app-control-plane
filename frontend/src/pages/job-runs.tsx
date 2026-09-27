import { useState } from "react";
import { api } from "../api";
import {
  ActionForm,
  Badge,
  Dialog,
  Field,
  Paged,
  date,
  number,
  text,
} from "../components";
import { useData } from "../state";

export type JobRun = {
  id: string;
  deployment_id: string;
  operation_id: string;
  resource_key: string;
  status: string;
  scenario: string;
  execution_mode: "simulated";
  parameters: { row_count: number };
  last_observed_at: string | null;
  result: {
    outcome: string;
    output: { rows: number; total: number } | null;
    output_verified: boolean;
  } | null;
};

export function RunDetails({ row }: { row: JobRun }) {
  return (
    <div className="run-details">
      <strong>
        {row.resource_key} · {row.status} · <Badge tone="blue">Simulated</Badge>
      </strong>
      <small className="record-id break-word">Run: {row.id}</small>
      <small className="record-id break-word">
        Deployment: {row.deployment_id}
      </small>
      <small className="record-id break-word">
        Operation: {row.operation_id}
      </small>
      <p>
        Rows requested: {row.parameters.row_count} · Scenario: {row.scenario}
      </p>
      <p>
        Last observed:{" "}
        {row.last_observed_at ? date(row.last_observed_at) : "Pending"}
      </p>
      {row.result?.output && (
        <p>
          Simulated output: {row.result.output.rows} rows, total{" "}
          {row.result.output.total}. Output verified:{" "}
          {row.result.output_verified ? "Yes" : "No"}.
        </p>
      )}
      {row.result?.outcome === "failure" && (
        <p>The simulated job failed. Deployment status is unchanged.</p>
      )}
    </div>
  );
}

export function RunHistory({ path }: { path: string }) {
  return (
    <Paged<JobRun> path={path} empty="No job runs yet">
      {(items) => (
        <ul className="attempt-list">
          {items.map((row) => (
            <li key={row.id}>
              <RunDetails row={row} />
            </li>
          ))}
        </ul>
      )}
    </Paged>
  );
}

export function RunControls({ deploymentId }: { deploymentId: string }) {
  const [open, setOpen] = useState(false);
  // A new deliberate run gets a new intent; transport retries retain its key.
  const [intent, setIntent] = useState(() => crypto.randomUUID());
  const { commandKey, notify, refresh } = useData();
  return (
    <>
      <button className="button secondary" onClick={() => setOpen(true)}>
        Run simulated job
      </button>
      {open && (
        <Dialog title="Run simulated job" onClose={() => setOpen(false)}>
          <p>
            Run synthetic_job from this successful deployment. This is a local
            simulation with no real compute.
          </p>
          <ActionForm
            submitLabel="Queue simulated run"
            onCancel={() => setOpen(false)}
            submit={async (data) => {
              const path = `/api/v1/deployments/${deploymentId}/runs`;
              const body = {
                resource_key: "synthetic_job",
                execution_mode: "simulated",
                parameters: { row_count: number(data, "row_count") },
                scenario: text(data, "scenario"),
              };
              const result = await api<{ operation_id: string }>(path, {
                method: "POST",
                body,
                key: commandKey(`${path}:${intent}:${JSON.stringify(body)}`),
              });
              notify(`Simulated run queued. Operation: ${result.operation_id}`);
              setOpen(false);
              setIntent(crypto.randomUUID());
              refresh();
            }}
          >
            <Field label="Synthetic row count">
              <input
                name="row_count"
                type="number"
                min={1}
                max={10000}
                step={1}
                defaultValue={100}
                required
              />
            </Field>
            <Field label="Run simulation scenario">
              <select name="scenario">
                <option value="success">Simulated success</option>
                <option value="failure">Simulated failure</option>
              </select>
            </Field>
            <p>
              After a lost response, retry this form. After a page reload,
              inspect run history before submitting again.
            </p>
          </ActionForm>
        </Dialog>
      )}
    </>
  );
}
