import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import {
  ActionForm,
  AddButton,
  Badge,
  date,
  Dialog,
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
import { useData, useResource, useSession } from "../state";

interface AccessRequest {
  id: string;
  application_id: string;
  requested_by: number;
  requested_role: string;
  reason: string;
  status: string;
  created_at: string;
  decision_reason: string | null;
  decided_at: string | null;
}
interface EffectiveAccess {
  user_id: number;
  is_active: boolean;
  can_read: boolean;
  roles: string[];
  relationships: string[];
  grants: { assignment_id: string; role: string; team_id: string | null }[];
}

export function RequestAccess({ applicationId }: { applicationId?: string }) {
  const [open, setOpen] = useState(false);
  const { refresh, notify } = useData();
  return (
    <>
      <AddButton onClick={() => setOpen(true)}>Request access</AddButton>
      {open && (
        <Dialog title="Request platform access" onClose={() => setOpen(false)}>
          <ActionForm
            submitLabel="Send request"
            onCancel={() => setOpen(false)}
            submit={async (data) => {
              const id = applicationId || text(data, "application_id");
              await api(
                `/api/v1/applications/${encodeURIComponent(id)}/access-requests`,
                {
                  method: "POST",
                  body: {
                    requested_role: text(data, "requested_role"),
                    reason: text(data, "reason"),
                  },
                },
              );
              setOpen(false);
              refresh();
              notify(
                "Access request sent. The application owner or an administrator can decide it.",
              );
            }}
          >
            {!applicationId && (
              <Field
                label="Application ID"
                hint="Ask the application owner for its ID."
              >
                <input
                  name="application_id"
                  required
                  maxLength={36}
                  pattern="[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
                />
              </Field>
            )}
            <Field label="Requested role">
              <select name="requested_role">
                {["viewer", "developer", "approver", "operator"].map((role) => (
                  <option key={role}>{role}</option>
                ))}
              </select>
            </Field>
            <Field
              label="Reason"
              hint="Explain why you need this platform role."
            >
              <textarea name="reason" required maxLength={2000} rows={3} />
            </Field>
            <p className="form-hint">
              This requests access for your account. Platform roles do not grant
              GitHub, Databricks or data permissions.
            </p>
          </ActionForm>
        </Dialog>
      )}
    </>
  );
}

export function AccessRequests({
  applicationId,
  canManage = false,
  archived = false,
}: {
  applicationId?: string;
  canManage?: boolean;
  archived?: boolean;
}) {
  const { user } = useSession();
  const { refresh, notify } = useData();
  const [action, setAction] = useState<{
    row: AccessRequest;
    decision: "approved" | "rejected" | "cancelled";
  } | null>(null);
  const path = applicationId
    ? `/api/v1/applications/${applicationId}/access-requests`
    : "/api/v1/access-requests";
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>{canManage ? "Access requests" : "My access requests"}</h2>
          <p>
            {canManage
              ? "Review requests for platform roles."
              : "Outcomes stay available here after access is revoked."}
          </p>
        </div>
        {!archived && <RequestAccess applicationId={applicationId} />}
      </div>
      <Paged<AccessRequest> path={path} empty="No access requests">
        {(items) => (
          <div className="access-requests">
            {items.map((row) => (
              <article className="access-request" key={row.id}>
                <div className="section-heading">
                  <div>
                    <h3>
                      User #{row.requested_by} · {row.requested_role}
                    </h3>
                    <p>Requested {date(row.created_at)}</p>
                  </div>
                  <Status value={row.status} />
                </div>
                {!applicationId && (
                  <p className="break-word">
                    Application ID: <code>{row.application_id}</code>
                  </p>
                )}
                <p className="break-word">{row.reason}</p>
                {row.decision_reason && (
                  <p className="break-word">
                    {row.decision_reason} · {date(row.decided_at)}
                  </p>
                )}
                {row.status === "approved" && (
                  <p className="form-hint">
                    This records the approval. Current access may have changed.{" "}
                    <Link to={`/applications/${row.application_id}`}>
                      Open application
                    </Link>
                  </p>
                )}
                {row.status === "pending" && (
                  <div className="actions">
                    {canManage && !archived && (
                      <>
                        <button
                          className="button secondary"
                          onClick={() =>
                            setAction({ row, decision: "approved" })
                          }
                        >
                          Approve request
                        </button>
                        <button
                          className="button secondary"
                          onClick={() =>
                            setAction({ row, decision: "rejected" })
                          }
                        >
                          Reject request
                        </button>
                      </>
                    )}
                    {row.requested_by === user?.id && (
                      <button
                        className="text-button"
                        onClick={() =>
                          setAction({ row, decision: "cancelled" })
                        }
                      >
                        Withdraw request
                      </button>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </Paged>
      {action && (
        <Dialog
          title={
            action.decision === "approved"
              ? "Approve access request"
              : action.decision === "rejected"
                ? "Reject access request"
                : "Withdraw access request"
          }
          onClose={() => setAction(null)}
        >
          <p>
            User #{action.row.requested_by} requested the{" "}
            {action.row.requested_role} role.
          </p>
          <ActionForm
            submitLabel={
              action.decision === "approved"
                ? "Approve access"
                : action.decision === "rejected"
                  ? "Reject access"
                  : "Withdraw request"
            }
            onCancel={() => setAction(null)}
            submit={async (data) => {
              await api(
                `/api/v1/access-requests/${action.row.id}/${action.decision === "cancelled" ? "cancel" : "decision"}`,
                {
                  method: "POST",
                  ...(action.decision === "cancelled"
                    ? {}
                    : {
                        body: {
                          decision: action.decision,
                          reason: text(data, "reason"),
                        },
                      }),
                },
              );
              setAction(null);
              refresh();
              notify("Access request updated.");
            }}
          >
            {action.decision !== "cancelled" && (
              <Field
                label="Decision reason"
                hint="This explanation is visible to the requester."
              >
                <textarea name="reason" required maxLength={2000} rows={3} />
              </Field>
            )}
          </ActionForm>
        </Dialog>
      )}
    </section>
  );
}

export function MyAccessRequests() {
  return (
    <>
      <PageHeader
        title="Access requests"
        description="Request a platform role and follow your request outcomes."
        actions={<RefreshButton />}
      />
      <AccessRequests />
    </>
  );
}

export function EffectiveAccessPanel({
  applicationId,
  userId,
}: {
  applicationId: string;
  userId: number;
}) {
  const resource = useResource<EffectiveAccess>(
    `/api/v1/applications/${applicationId}/effective-access/${userId}`,
  );
  const access = resource.data;
  return (
    <div className="panel-body" aria-live="polite">
      <h3>Effective access for user #{userId}</h3>
      <ErrorNotice error={resource.error} />
      {resource.loading ? (
        <Loading />
      ) : (
        access &&
        !resource.error && (
          <>
            <p>
              {access.can_read
                ? "Access retained: this user can read the application."
                : "No effective access: this user cannot read the application."}
            </p>
            {!access.is_active && (
              <p>
                The account is inactive; its assignments grant no current
                access.
              </p>
            )}
            <p>Current roles: {access.roles.join(", ") || "none"}.</p>
            {access.relationships.length > 0 && (
              <p>
                Read access through:{" "}
                {access.relationships
                  .map((value) => value.replaceAll("_", " "))
                  .join(", ")}
                . Changing role assignments does not remove these relationships.
              </p>
            )}
            {access.grants.length > 0 && (
              <ul>
                {access.grants.map((grant) => (
                  <li key={grant.assignment_id} className="break-word">
                    <Badge>{grant.role}</Badge>{" "}
                    {grant.team_id
                      ? `Through team ${grant.team_id}`
                      : "Direct assignment"}
                  </li>
                ))}
              </ul>
            )}
          </>
        )
      )}
    </div>
  );
}

export function AccessInspector({
  applicationId,
  canManage,
  selectedUser,
  onSelect,
}: {
  applicationId: string;
  canManage: boolean;
  selectedUser: number | null;
  onSelect: (userId: number) => void;
}) {
  const { user } = useSession();
  const userId = selectedUser ?? user!.id;
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Effective access</h2>
          <p>
            Direct roles, team grants and ownership all contribute to access.
          </p>
        </div>
      </div>
      {canManage && (
        <div className="panel-body">
          <ActionForm
            submitLabel="Check access"
            submit={async (data) => onSelect(number(data, "user_id"))}
          >
            <Field label="Inspect user ID">
              <input
                key={userId}
                type="number"
                name="user_id"
                min={1}
                required
                defaultValue={userId}
              />
            </Field>
          </ActionForm>
        </div>
      )}
      <EffectiveAccessPanel applicationId={applicationId} userId={userId} />
    </section>
  );
}
