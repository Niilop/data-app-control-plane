import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  FolderOpen,
  LoaderCircle,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { APIError } from "./api";
import { useData, usePage } from "./state";

export const date = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not yet observed";
export const label = (value: string) => value.replaceAll("_", " ");
export function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Status({ value }: { value: string }) {
  return (
    <Badge
      tone={
        ["succeeded", "active", "success"].includes(value)
          ? "green"
          : ["failed", "needs_attention"].includes(value)
            ? "red"
            : ["running", "reconciling", "queued", "retry_wait"].includes(value)
              ? "blue"
              : ""
      }
    >
      {label(value)}
    </Badge>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={20} /> Loading…
    </div>
  );
}
export function ErrorNotice({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div className="alert error" role="alert">
      <CircleAlert size={18} />
      <div>
        {error.message}
        {error instanceof APIError && error.requestId && (
          <small>Request ID: {error.requestId}</small>
        )}
      </div>
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FolderOpen size={28} />
      </div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="actions">{actions}</div>
    </header>
  );
}
export function RefreshButton() {
  const { refresh } = useData();
  return (
    <button className="button secondary" onClick={refresh}>
      <RefreshCw size={16} />
      Refresh
    </button>
  );
}
export function AddButton({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className="button primary" onClick={onClick}>
      <Plus size={17} />
      {children}
    </button>
  );
}
export function Dialog({
  title,
  children,
  onClose,
  description,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  description?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const element = ref.current;
    const opener = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={id}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="dialog-header">
        <div>
          <h2 id={id}>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Field({
  label: text,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{text}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function ActionForm({
  children,
  submit,
  onCancel,
  submitLabel = "Save changes",
  disabled = false,
}: {
  children: ReactNode;
  submit: (form: FormData) => Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const pending = useRef(false);
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (pending.current || disabled) return;
        const data = new FormData(event.currentTarget);
        pending.current = true;
        setBusy(true);
        setError(null);
        try {
          await submit(data);
        } catch (error) {
          setError(
            error instanceof Error ? error : new Error("Request failed"),
          );
        } finally {
          pending.current = false;
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy}>{children}</fieldset>
      <ErrorNotice error={error} />
      <div className="form-actions">
        {onCancel && (
          <button className="button secondary" type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button
          className="button primary"
          disabled={busy || disabled}
          type="submit"
        >
          {busy && <LoaderCircle size={16} className="spin" />}
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
export function Paged<T>({
  path,
  children,
  empty = "No records yet",
  description,
}: {
  path: string;
  children: (items: T[], loading: boolean) => ReactNode;
  empty?: string;
  description?: string;
}) {
  const page = usePage<T>(path);
  return (
    <>
      <ErrorNotice error={page.error} />
      {page.loading && page.data && (
        <div className="loading" role="status">
          <LoaderCircle size={16} className="spin" />
          Refreshing records…
        </div>
      )}
      {page.loading && !page.data ? (
        <Loading />
      ) : (
        page.data &&
        (page.data.items.length ? (
          children(page.data.items, page.loading)
        ) : (
          <Empty title={empty}>{description}</Empty>
        ))
      )}
      {page.data && (
        <div className="pagination">
          <span>{page.data.items.length} records on this page</span>
          <div>
            <button
              className="button small secondary"
              onClick={page.previous}
              disabled={page.page === 1 || page.loading}
            >
              <ArrowLeft size={14} />
              Previous
            </button>
            <span>Page {page.page}</span>
            <button
              className="button small secondary"
              onClick={page.next}
              disabled={!page.data.next_cursor || page.loading}
            >
              Next
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
export const text = (data: FormData, name: string) =>
  String(data.get(name) ?? "").trim();
export const number = (data: FormData, name: string) => Number(data.get(name));
